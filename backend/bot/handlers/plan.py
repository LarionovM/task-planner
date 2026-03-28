"""Обработчики /plan и /next — план на день и ближайшая задача."""

import logging
from datetime import date, datetime, timedelta, time

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from backend.db.database import async_session
from backend.db.crud.users import get_or_create_user
from backend.db.crud.blocks import get_blocks_for_day, list_blocks_for_week
from backend.db.crud.tasks import get_task, list_categories
from backend.db.models import AllowedUser

logger = logging.getLogger(__name__)

router = Router()

# Маппинг статусов на эмодзи
STATUS_EMOJI = {
    "planned": "⬜",
    "active": "▶️",
    "done": "✅",
    "partial": "⚡",
    "failed": "❌",
    "skipped": "⏭",
}


def _format_duration(block) -> str:
    """Форматирует длительность блока."""
    if block.duration_type == "fixed":
        return f"{block.duration_min}м"
    elif block.duration_type == "open":
        if block.max_duration_min:
            return f"~{block.max_duration_min}м"
        return "откр."
    elif block.duration_type == "range":
        return f"{block.min_duration_min}–{block.max_duration_min}м"
    return ""


def _time_str(t: str | time) -> str:
    """Преобразует время в строку HH:MM."""
    if isinstance(t, time):
        return t.strftime("%H:%M")
    return str(t)[:5]


async def _get_block_info(session, block, user_id: int, categories: dict) -> str:
    """Формирует строку описания блока."""
    status = STATUS_EMOJI.get(block.status, "⬜")
    start = _time_str(block.start_time)
    dur = _format_duration(block)
    name = block.block_name or "Без названия"

    # Получаем категорию из первой задачи
    cat_info = ""
    if block.task_ids:
        task = await get_task(session, block.task_ids[0], user_id)
        if task:
            cat = categories.get(task.category_id)
            if cat:
                cat_info = f" {cat.emoji or ''}"
            if not block.block_name:
                name = task.name

    return f"{status} `{start}` {name}{cat_info} ({dur})"


async def _format_day_plan_grouped(
    session, blocks: list, user_id: int, categories: dict
) -> tuple[list[str], int, int, int, int]:
    """Формирует сгруппированный по слотам план дня.

    Возвращает: (lines, block_count, done_count, total_min, task_count)
    block_count — кол-во уникальных блоков (дедуплицированных)
    task_count — суммарное кол-во задач (с учётом дубликатов в task_ids)
    """
    from collections import Counter, OrderedDict

    lines: list[str] = []
    done_count = 0
    total_min = 0
    total_task_count = 0

    # Считаем уникальные задачи по всем блокам (без дубликатов от multi_per_block)
    all_unique_task_ids: set[int] = set()
    for block in blocks:
        if block.task_ids:
            all_unique_task_ids.update(block.task_ids)
    total_task_count = len(all_unique_task_ids)

    # Группируем блоки по start_time
    slots: OrderedDict[str, list] = OrderedDict()
    for block in blocks:
        key = _time_str(block.start_time)
        if key not in slots:
            slots[key] = []
        slots[key].append(block)

    for slot_time, slot_blocks in slots.items():
        # Считаем статистику
        for block in slot_blocks:
            if block.status in ("done", "partial"):
                done_count += 1
            if block.actual_duration_min is not None:
                total_min += block.actual_duration_min
            elif block.duration_type == "fixed":
                total_min += block.duration_min or 0
            elif block.duration_type == "range":
                total_min += ((block.min_duration_min or 0) + (block.max_duration_min or 0)) // 2
            else:
                total_min += block.max_duration_min or 30

        # Определяем общий статус слота
        statuses = [b.status for b in slot_blocks]
        if all(s == "done" for s in statuses):
            slot_status = "✅"
        elif any(s == "active" for s in statuses):
            slot_status = "▶️"
        elif any(s in ("done", "partial") for s in statuses):
            slot_status = "⚡"
        elif any(s == "failed" for s in statuses):
            slot_status = "❌"
        elif any(s == "skipped" for s in statuses):
            slot_status = "⏭"
        else:
            slot_status = "⬜"

        # Суммарная длительность слота
        slot_dur = 0
        for b in slot_blocks:
            if b.duration_type == "fixed":
                slot_dur += b.duration_min or 0
            elif b.duration_type == "range":
                slot_dur += ((b.min_duration_min or 0) + (b.max_duration_min or 0)) // 2
            else:
                slot_dur += b.max_duration_min or 30

        if slot_dur >= 60:
            dur_str = f"{slot_dur // 60}ч{slot_dur % 60}м" if slot_dur % 60 else f"{slot_dur // 60}ч"
        else:
            dur_str = f"{slot_dur}м"

        # Собираем описания блоков в слоте
        # Каждый блок — отдельная единица; внутри блока считаем ×N для дубликатов task_ids
        block_entries: list[tuple[str, str]] = []  # (description, cat_emoji)

        for block in slot_blocks:
            if block.task_ids:
                # Уникальные task_ids (без дубликатов от allow_multi_per_block)
                unique_ids = list(dict.fromkeys(block.task_ids))
                parts_list = []
                first_emoji = ""
                for tid in unique_ids:
                    task = await get_task(session, tid, user_id)
                    if task:
                        cat = categories.get(task.category_id)
                        if cat and not first_emoji:
                            first_emoji = cat.emoji or ""
                        parts_list.append(task.name)
                desc = ", ".join(parts_list) if parts_list else (block.block_name or "Без названия")
                block_entries.append((desc, first_emoji))
            else:
                block_entries.append((block.block_name or "Без названия", ""))

        # Группируем одинаковые блоки (дубликаты от auto-distribute)
        unique_entries: list[tuple[str, str, int]] = []  # (desc, emoji, count)
        seen: dict[str, int] = {}
        for desc, emoji in block_entries:
            if desc in seen:
                idx = seen[desc]
                d, e, c = unique_entries[idx]
                unique_entries[idx] = (d, e, c + 1)
            else:
                seen[desc] = len(unique_entries)
                unique_entries.append((desc, emoji, 1))

        # Длительность показываем от ОДНОГО блока (не суммарную от дубликатов)
        single_block = slot_blocks[0]
        if single_block.duration_type == "fixed":
            single_dur = single_block.duration_min or 0
        elif single_block.duration_type == "range":
            single_dur = ((single_block.min_duration_min or 0) + (single_block.max_duration_min or 0)) // 2
        else:
            single_dur = single_block.max_duration_min or 30

        if single_dur >= 60:
            dur_str = f"{single_dur // 60}ч{single_dur % 60}м" if single_dur % 60 else f"{single_dur // 60}ч"
        else:
            dur_str = f"{single_dur}м"

        if len(unique_entries) == 1:
            desc, emoji, count = unique_entries[0]
            count_str = f" ×{count}" if count > 1 else ""
            emoji_str = f"{emoji} " if emoji else ""
            lines.append(f"{slot_status} `{slot_time}` {emoji_str}{desc}{count_str} ({dur_str})")
        else:
            lines.append(f"{slot_status} `{slot_time}` ({dur_str})")
            for desc, emoji, count in unique_entries:
                count_str = f" ×{count}" if count > 1 else ""
                emoji_str = f"{emoji} " if emoji else ""
                lines.append(f"    {emoji_str}{desc}{count_str}")

    # Считаем уникальные блоки (дедуплицированные)
    # Группируем по (start_time, block_name/description) — дубликаты от auto-distribute считаются как один
    seen_blocks: set[str] = set()
    for block in blocks:
        key = f"{_time_str(block.start_time)}_{block.block_name or ''}_{','.join(str(t) for t in (block.task_ids or []))}"
        seen_blocks.add(key)
    block_count = len(seen_blocks)

    return lines, block_count, done_count, total_min, total_task_count


@router.message(Command("plan"))
async def cmd_plan(message: Message, allowed_user: AllowedUser):
    """План на день. Опции: /plan, /plan завтра, /plan 2 (послезавтра)."""
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    target_day = date.today()
    day_label = "сегодня"

    if len(parts) > 1:
        arg = parts[1].strip().lower()
        if arg in ("завтра", "tomorrow", "1"):
            target_day += timedelta(days=1)
            day_label = "завтра"
        elif arg in ("послезавтра", "2"):
            target_day += timedelta(days=2)
            day_label = "послезавтра"
        elif arg in ("вчера", "yesterday", "-1"):
            target_day -= timedelta(days=1)
            day_label = "вчера"
        elif arg in ("неделя", "week", "нед"):
            # Показать план на всю неделю
            await _send_week_plan(message, allowed_user)
            return
        else:
            # Попробуем как число дней
            try:
                days_offset = int(arg)
                target_day += timedelta(days=days_offset)
                day_label = target_day.strftime("%d.%m")
            except ValueError:
                await message.answer(
                    "📅 *Использование:*\n"
                    "`/plan` — план на сегодня\n"
                    "`/plan завтра` — на завтра\n"
                    "`/plan 2` — через 2 дня\n"
                    "`/plan неделя` — на всю неделю",
                    parse_mode="Markdown",
                )
                return

    async with async_session() as session:
        blocks = await get_blocks_for_day(session, allowed_user.telegram_id, target_day)
        categories_list = await list_categories(session, allowed_user.telegram_id)
        cat_map = {c.id: c for c in categories_list}

        if not blocks:
            weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            wd = weekday_names[target_day.weekday()]
            await message.answer(
                f"📅 *План на {day_label}* ({wd}, {target_day.strftime('%d.%m')})\n\n"
                "Нет запланированных блоков.\n"
                "Открой планировщик чтобы добавить задачи!",
                parse_mode="Markdown",
            )
            return

        # Формируем план
        weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        wd = weekday_names[target_day.weekday()]
        lines = [f"📅 *План на {day_label}* ({wd}, {target_day.strftime('%d.%m')})\n"]

        block_lines, block_count, done_count, total_min, task_count = await _format_day_plan_grouped(
            session, blocks, allowed_user.telegram_id, cat_map
        )
        lines.extend(block_lines)

        # Итого
        hours = total_min // 60
        mins = total_min % 60
        time_str = f"{hours}ч {mins}мин" if hours else f"{mins}мин"

        lines.append("")
        lines.append(f"📊 Всего: {block_count} блоков, {task_count} задач, ~{time_str}")
        if done_count > 0:
            lines.append(f"✅ Выполнено: {done_count}/{block_count}")

    await message.answer("\n".join(lines), parse_mode="Markdown")


async def _send_week_plan(message: Message, allowed_user: AllowedUser):
    """Краткий план на неделю."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    async with async_session() as session:
        blocks = await list_blocks_for_week(session, allowed_user.telegram_id, week_start)
        categories_list = await list_categories(session, allowed_user.telegram_id)
        cat_map = {c.id: c for c in categories_list}

    weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    lines = [f"📅 *План на неделю* ({week_start.strftime('%d.%m')}–{(week_start + timedelta(days=6)).strftime('%d.%m')})\n"]

    for i in range(7):
        day = week_start + timedelta(days=i)
        day_blocks = [b for b in blocks if str(b.day) == str(day)]
        wd = weekday_names[i]
        is_today = day == today

        if not day_blocks:
            marker = " 👈" if is_today else ""
            lines.append(f"*{wd}*{marker} — свободно")
        else:
            done = sum(1 for b in day_blocks if b.status in ("done", "partial"))

            # Считаем уникальные блоки (дедуплицированные)
            seen_keys: set[str] = set()
            for b in day_blocks:
                key = f"{_time_str(b.start_time)}_{b.block_name or ''}_{','.join(str(t) for t in (b.task_ids or []))}"
                seen_keys.add(key)
            block_count = len(seen_keys)

            # Считаем уникальные задачи (без дубликатов от multi_per_block)
            day_task_ids: set[int] = set()
            for b in day_blocks:
                if b.task_ids:
                    day_task_ids.update(b.task_ids)
            task_count = len(day_task_ids)

            total_min = 0
            for b in day_blocks:
                if b.actual_duration_min is not None:
                    total_min += b.actual_duration_min
                elif b.duration_type == "fixed":
                    total_min += b.duration_min or 0
                else:
                    total_min += b.max_duration_min or 30

            h = total_min // 60
            m = total_min % 60
            time_s = f"{h}ч{m}м" if h else f"{m}м"
            marker = " 👈" if is_today else ""
            progress = f" ({done}✅)" if done > 0 else ""
            lines.append(f"*{wd}*{marker} — {block_count} бл., {task_count} задач, ~{time_s}{progress}")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("next"))
async def cmd_next(message: Message, allowed_user: AllowedUser):
    """Ближайший предстоящий блок."""
    now = datetime.now()
    today = now.date()
    current_time = now.time()

    async with async_session() as session:
        categories_list = await list_categories(session, allowed_user.telegram_id)
        cat_map = {c.id: c for c in categories_list}

        # Ищем на сегодня и ближайшие 7 дней
        next_block = None
        next_day = None

        for offset in range(8):
            day = today + timedelta(days=offset)
            blocks = await get_blocks_for_day(session, allowed_user.telegram_id, day)

            for block in blocks:
                if block.status not in ("planned",):
                    continue

                # Для сегодня — только будущие блоки
                if day == today:
                    block_time = block.start_time
                    if isinstance(block_time, str):
                        h, m = map(int, block_time.split(":")[:2])
                        block_time = time(h, m)
                    if block_time <= current_time:
                        continue

                next_block = block
                next_day = day
                break

            if next_block:
                break

        if not next_block:
            await message.answer(
                "📋 *Ближайший блок*\n\n"
                "Нет предстоящих блоков на ближайшую неделю.\n"
                "Создай задачи в планировщике!",
                parse_mode="Markdown",
            )
            return

        # Формируем подробную информацию
        info = await _get_block_info(session, next_block, allowed_user.telegram_id, cat_map)

        # Длительность блока
        block_dur = _format_duration(next_block)

        # Считаем оставшееся время
        weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        wd = weekday_names[next_day.weekday()]

        block_time = next_block.start_time
        if isinstance(block_time, str):
            h, m = map(int, block_time.split(":")[:2])
            block_time = time(h, m)

        block_dt = datetime.combine(next_day, block_time)
        delta = block_dt - now

        if delta.total_seconds() < 60:
            time_until = "сейчас!"
        elif delta.total_seconds() < 3600:
            time_until = f"через {int(delta.total_seconds() // 60)} мин"
        elif delta.days == 0:
            hours = int(delta.total_seconds() // 3600)
            mins = int((delta.total_seconds() % 3600) // 60)
            time_until = f"через {hours}ч {mins}мин"
        elif delta.days == 1:
            time_until = f"завтра в {_time_str(next_block.start_time)}"
        else:
            time_until = f"{wd}, {next_day.strftime('%d.%m')} в {_time_str(next_block.start_time)}"

        # Подробности задач в блоке
        task_details = []
        unique_task_ids = list(dict.fromkeys(next_block.task_ids)) if next_block.task_ids else []
        task_count = len(unique_task_ids)

        for tid in unique_task_ids[:5]:  # Максимум 5 задач
            task = await get_task(session, tid, allowed_user.telegram_id)
            if task:
                prio = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task.priority, "")
                task_details.append(f"  • {prio} {task.name}")

        lines = [
            "📋 *Ближайший блок*\n",
            info,
            f"\n⏰ {time_until}",
        ]

        if task_details:
            task_word = "задача" if task_count == 1 else "задач" if task_count >= 5 else "задачи"
            lines.append(f"\n📝 *{task_count} {task_word} в блоке:*")
            lines.extend(task_details)

        # Также покажем активный блок, если есть
        active_blocks = await get_blocks_for_day(session, allowed_user.telegram_id, today)
        active = [b for b in active_blocks if b.status == "active"]
        if active:
            lines.append("\n▶️ *Сейчас активно:*")
            for ab in active:
                ab_info = await _get_block_info(session, ab, allowed_user.telegram_id, cat_map)
                lines.append(ab_info)

    await message.answer("\n".join(lines), parse_mode="Markdown")

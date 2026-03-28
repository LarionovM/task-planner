"""Все типы напоминаний и спам-машина.

Отправка уведомлений пользователю через Telegram:
- Подготовка (за N мин до старта)
- Старт блока (fixed/open/range)
- Завершение блока / опросник
- Min duration reached (range)
- Max duration reminder (open/range)
- Pomodoro break/resume
- Итог дня
- Восстановление после рестарта
- Экспоненциальный спам
"""

import asyncio
import logging
from datetime import datetime, date, time, timedelta
from collections import Counter
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from backend.config import (
    POMODORO_WORK_MIN,
    POMODORO_BREAK_MIN,
    SPAM_TEXTS,
    SPAM_QUESTIONNAIRE_TIMEOUT_SEC,
)
from backend.db.database import async_session
from backend.db.crud.blocks import (
    get_block,
    create_log,
    get_blocks_for_day,
)
from backend.db.crud.users import get_or_create_user, get_spam_config
from backend.db.crud.tasks import get_task, list_categories
from backend.db.models import TaskBlock

logger = logging.getLogger(__name__)

# === Хранилище спам-сообщений в памяти ===
# {user_id: list[message_id]} — для удаления при ответе
_spam_messages: dict[int, list[int]] = {}

# {user_id: asyncio.Task} — активные спам-таски
_spam_tasks: dict[int, asyncio.Task] = {}


# === Вспомогательные ===


async def _get_block_info(block_id: int) -> tuple[TaskBlock | None, dict]:
    """Получает блок и мета-информацию (название, категории, задачи)."""
    async with async_session() as session:
        # Нужно найти блок без user_id — ищем напрямую
        from sqlalchemy import select
        from backend.db.models import TaskBlock as TB
        result = await session.execute(select(TB).where(TB.id == block_id))
        block = result.scalar_one_or_none()
        if not block:
            return None, {}

        user = await get_or_create_user(session, block.user_id)
        categories = await list_categories(session, block.user_id)
        cat_map = {c.id: c for c in categories}

        # Информация о задачах
        task_names = []
        task_categories = set()
        tasks_list = []
        first_cat_str = ""
        for tid in set(block.task_ids or []):
            task = await get_task(session, tid, block.user_id)
            if task:
                tasks_list.append(task)
                task_names.append(task.name)
                cat = cat_map.get(task.category_id)
                if cat:
                    cat_str = f"{cat.emoji or ''} {cat.name}"
                    task_categories.add(cat_str)
                    if not first_cat_str:
                        first_cat_str = cat_str

        return block, {
            "user": user,
            "task_names": task_names,
            "task_categories": task_categories,
            "first_cat": first_cat_str,
            "tasks": tasks_list,
            "cat_map": cat_map,
        }


def _duration_text(block: TaskBlock) -> str:
    """Текстовое описание длительности."""
    if block.duration_type == "fixed":
        return f"{block.duration_min} мин"
    elif block.duration_type == "open":
        return "открытый"
    elif block.duration_type == "range":
        return f"{block.min_duration_min}–{block.max_duration_min} мин"
    return "?"


def _block_header(block: TaskBlock, info: dict) -> str:
    """Формирует заголовок блока: '08:30-10:00 📚 Обучение: Группа — Задача'.

    Формат: {время начала}-{время конца} {Категория}: {(опц.) группа} — {задачи}
    """
    # Время начала
    st = block.start_time
    if isinstance(st, str):
        h, m = map(int, st.split(":")[:2])
        st = time(h, m)
    start_str = st.strftime("%H:%M")

    # Время конца (расчёт по длительности)
    if block.duration_type == "fixed":
        dur = block.duration_min or 60
    elif block.duration_type == "range":
        dur = block.max_duration_min or 60
    else:
        dur = block.max_duration_min or 60
    end_dt = datetime.combine(date.today(), st) + timedelta(minutes=dur)
    end_str = end_dt.strftime("%H:%M")

    # Категория
    cat_str = info.get("first_cat", "")

    # Название группы (block_name) и задачи
    group_name = block.block_name or ""
    task_names = info.get("task_names", [])

    # Собираем с учётом дубликатов в task_ids
    task_counts = Counter(block.task_ids or [])
    task_parts = []
    for t in info.get("tasks", []):
        count = task_counts.get(t.id, 1)
        if count > 1:
            task_parts.append(f"{t.name} ×{count}")
        else:
            task_parts.append(t.name)
    tasks_str = ", ".join(task_parts) if task_parts else ""

    # Формируем строку
    parts = [f"{start_str}-{end_str}"]
    if cat_str:
        parts.append(cat_str)

    header = " ".join(parts)

    # Добавляем группу и задачи
    if group_name and tasks_str and group_name != tasks_str:
        header += f": {group_name} — {tasks_str}"
    elif group_name:
        header += f": {group_name}"
    elif tasks_str:
        header += f": {tasks_str}"

    return header


def _is_in_quiet_time(t: time, quiet_start: time, quiet_end: time) -> bool:
    """Попадает ли время в тихое время."""
    if quiet_start <= quiet_end:
        return quiet_start <= t <= quiet_end
    else:
        return t >= quiet_start or t <= quiet_end


def _is_in_working_hours(t: time, schedule_list) -> bool:
    """Проверяет, попадает ли текущее время в рабочие часы (по дню недели)."""
    now_weekday = datetime.now().weekday()
    for s in schedule_list:
        if s.day_of_week == now_weekday:
            if s.is_day_off:
                return False
            return s.active_from <= t <= s.active_to
    return True


# === Уведомления ===


async def send_prep_reminder(block_id: int) -> None:
    """Уведомление подготовки (за N мин до старта)."""
    from backend.bot.scheduler import get_bot

    block, info = await _get_block_info(block_id)
    if not block or block.status != "planned":
        return

    bot = get_bot()
    user = info["user"]
    header = _block_header(block, info)

    # Считаем минут до старта
    tz = ZoneInfo(user.timezone or "Europe/Moscow")
    now = datetime.now(tz)
    start_dt = datetime.combine(block.day, block.start_time).replace(tzinfo=tz)
    mins_left = max(1, int((start_dt - now).total_seconds() / 60))

    text = (
        f"⏰ Через {mins_left} мин:\n"
        f"*{header}*\n"
        f"Подготовься: вода, поза, фокус 🎯"
    )

    await bot.send_message(block.user_id, text, parse_mode="Markdown")

    # Логируем
    async with async_session() as session:
        await create_log(session, block.user_id, "reminder_prep",
                         task_block_id=block.id, payload={"minutes_before": mins_left})
        await session.commit()


async def send_start_reminder(block_id: int) -> None:
    """Уведомление старта блока — разное для fixed/open/range."""
    from backend.bot.scheduler import get_bot

    block, info = await _get_block_info(block_id)
    if not block or block.status != "planned":
        return

    bot = get_bot()
    header = _block_header(block, info)

    # Обновляем статус на active
    async with async_session() as session:
        from sqlalchemy import select
        from backend.db.models import TaskBlock as TB
        result = await session.execute(select(TB).where(TB.id == block_id))
        db_block = result.scalar_one_or_none()
        if db_block:
            db_block.status = "active"
            if block.duration_type in ("open", "range"):
                db_block.actual_start_at = datetime.now()
            await create_log(session, block.user_id, "block_active",
                             task_block_id=block.id)
            await session.commit()

    # Формируем текст и кнопки
    if block.duration_type == "fixed":
        has_pomodoro = False
        if info["tasks"]:
            has_pomodoro = any(t.use_pomodoro for t in info["tasks"])

        text = f"🚀 *{header}*"
        if has_pomodoro:
            text += "\n🍅 Первый 25-мин фокус"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⏹ Завершить досрочно",
                callback_data=f"block_finish_early:{block.id}",
            )],
        ])

    elif block.duration_type == "open":
        text = f"🚀 *{header}*\n⏱ Открытый блок — нажми «Завершить» когда закончишь"
        if block.max_duration_min:
            text += f"\n⏰ Напомню через {block.max_duration_min} мин"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Завершить",
                callback_data=f"block_finish:{block.id}",
            )],
        ])

    elif block.duration_type == "range":
        text = f"🚀 *{header}*\n⏱ {block.min_duration_min}–{block.max_duration_min} мин"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⏹ Завершить досрочно",
                callback_data=f"block_finish_early:{block.id}",
            )],
        ])
    else:
        return

    await bot.send_message(block.user_id, text, reply_markup=keyboard, parse_mode="Markdown")

    async with async_session() as session:
        await create_log(session, block.user_id, "reminder_start",
                         task_block_id=block.id)
        await session.commit()


async def send_block_end_questionnaire(block_id: int) -> None:
    """Опросник по окончании блока: Выполнено / Частично / Не выполнено."""
    from backend.bot.scheduler import get_bot

    block, info = await _get_block_info(block_id)
    if not block or block.status not in ("active", "planned"):
        return

    bot = get_bot()
    header = _block_header(block, info)

    text = f"🏁 Время вышло: *{header}*\nКак прошло?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выполнено", callback_data=f"quest_done:{block.id}"),
            InlineKeyboardButton(text="⚡ Частично", callback_data=f"quest_partial:{block.id}"),
            InlineKeyboardButton(text="❌ Не выполнено", callback_data=f"quest_failed:{block.id}"),
        ],
    ])

    msg = await bot.send_message(block.user_id, text, reply_markup=keyboard, parse_mode="Markdown")

    # Через SPAM_QUESTIONNAIRE_TIMEOUT_SEC запустить спам если нет ответа
    asyncio.get_event_loop().call_later(
        SPAM_QUESTIONNAIRE_TIMEOUT_SEC,
        lambda: asyncio.ensure_future(_maybe_start_spam(block.user_id, block_id, msg.message_id)),
    )


async def send_min_duration_reached(block_id: int) -> None:
    """Для range блоков: минимальное время прошло, можно завершать."""
    from backend.bot.scheduler import get_bot

    block, info = await _get_block_info(block_id)
    if not block or block.status != "active":
        return

    bot = get_bot()
    header = _block_header(block, info)
    text = f"✅ Минимальное время прошло: *{header}*\nМожешь завершать когда будет готово."

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Завершить",
            callback_data=f"block_finish:{block.id}",
        )],
    ])

    await bot.send_message(block.user_id, text, reply_markup=keyboard, parse_mode="Markdown")


async def send_max_duration_reminder(block_id: int) -> None:
    """Напоминание при превышении max_duration (open и range)."""
    from backend.bot.scheduler import get_bot

    block, info = await _get_block_info(block_id)
    if not block or block.status != "active":
        return

    bot = get_bot()
    header = _block_header(block, info)

    # Считаем сколько минут прошло
    if block.actual_start_at:
        elapsed = int((datetime.now() - block.actual_start_at).total_seconds() / 60)
    else:
        elapsed = block.max_duration_min or 0

    text = f"⏰ Ты уже {elapsed} мин: *{header}*\nНе забыл завершить?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Завершить",
            callback_data=f"block_finish:{block.id}",
        )],
    ])

    await bot.send_message(block.user_id, text, reply_markup=keyboard, parse_mode="Markdown")

    async with async_session() as session:
        await create_log(session, block.user_id, "max_time_reminder",
                         task_block_id=block.id, payload={"elapsed_min": elapsed})
        await session.commit()


# === Pomodoro ===


async def schedule_pomodoro_jobs(block: TaskBlock, user_tz: str, now: datetime) -> None:
    """Планирует pomodoro-циклы (25+5) для fixed блока."""
    from backend.bot.scheduler import _safe_add_job, _make_job_id, _combine_user_dt

    duration = block.duration_min or 60
    block_start = _combine_user_dt(block.day, block.start_time, user_tz)
    cycle_len = POMODORO_WORK_MIN + POMODORO_BREAK_MIN  # 30 мин
    num_cycles = duration // cycle_len

    for i in range(num_cycles):
        # Перерыв после 25 мин работы
        break_dt = block_start + timedelta(minutes=i * cycle_len + POMODORO_WORK_MIN)
        if break_dt > now:
            job_id = _make_job_id(block.id, f"pomo_break_{i}")
            _safe_add_job(
                send_pomodoro_break,
                run_date=break_dt,
                args=[block.id, i + 1],
                id=job_id,
            )

        # Возобновление через 5 мин
        resume_dt = break_dt + timedelta(minutes=POMODORO_BREAK_MIN)
        # Не планируем resume если это конец блока
        if resume_dt > now and resume_dt < block_start + timedelta(minutes=duration):
            job_id = _make_job_id(block.id, f"pomo_resume_{i}")
            _safe_add_job(
                send_pomodoro_resume,
                run_date=resume_dt,
                args=[block.id, i + 1],
                id=job_id,
            )


async def send_pomodoro_break(block_id: int, cycle: int) -> None:
    """Уведомление о pomodoro-перерыве."""
    from backend.bot.scheduler import get_bot

    block, info = await _get_block_info(block_id)
    if not block or block.status != "active":
        return

    bot = get_bot()
    text = (
        f"⏸ {POMODORO_WORK_MIN} мин фокуса — стоп!\n"
        f"Перерыв {POMODORO_BREAK_MIN} мин: встань, пройдись, подыши 🌿"
    )
    await bot.send_message(block.user_id, text)

    async with async_session() as session:
        await create_log(session, block.user_id, "pomodoro_break",
                         task_block_id=block.id, payload={"cycle": cycle})
        await session.commit()


async def send_pomodoro_resume(block_id: int, cycle: int) -> None:
    """Уведомление о продолжении после pomodoro-перерыва."""
    from backend.bot.scheduler import get_bot

    block, info = await _get_block_info(block_id)
    if not block or block.status != "active":
        return

    bot = get_bot()
    text = "🍅 Поехали! Следующие 25 мин фокуса."
    await bot.send_message(block.user_id, text)

    async with async_session() as session:
        await create_log(session, block.user_id, "pomodoro_resume",
                         task_block_id=block.id, payload={"cycle": cycle})
        await session.commit()


# === Спам-машина ===


async def _maybe_start_spam(user_id: int, block_id: int, questionnaire_msg_id: int) -> None:
    """Проверяет нужно ли запускать спам (тройная проверка) и запускает."""
    from backend.bot.scheduler import get_bot
    from backend.db.crud.blocks import get_weekly_schedule

    block, info = await _get_block_info(block_id)
    if not block or block.status not in ("active", "planned"):
        return

    # Если блок уже завершён — спам не нужен
    if block.status in ("done", "skipped", "failed"):
        return

    async with async_session() as session:
        # 1. spam_config.enabled
        spam_config = await get_spam_config(session, user_id)
        if not spam_config or not spam_config.enabled:
            return

        # 2. Категория блока в spam_category_ids (пусто = все)
        if spam_config.spam_category_ids:
            block_cat_ids = set()
            for task in info.get("tasks", []):
                block_cat_ids.add(task.category_id)
            if not block_cat_ids.intersection(set(spam_config.spam_category_ids)):
                return

        # 3. task.spam_enabled для задач в блоке
        tasks = info.get("tasks", [])
        if tasks and not any(t.spam_enabled for t in tasks):
            return

        # 4. Проверяем рабочее время и тихое время
        user = info["user"]
        tz = ZoneInfo(user.timezone or "Europe/Moscow")
        now = datetime.now(tz)
        current_time = now.time()

        if _is_in_quiet_time(current_time, user.quiet_start, user.quiet_end):
            return

        schedule = await get_weekly_schedule(session, user_id)
        if not _is_in_working_hours(current_time, schedule):
            return

    # Запускаем спам
    await _start_spam_loop(user_id, block_id, spam_config)


async def _start_spam_loop(user_id: int, block_id: int, spam_config) -> None:
    """Запускает экспоненциальный спам."""
    from backend.bot.scheduler import get_bot

    # Отменяем предыдущий спам если есть
    if user_id in _spam_tasks:
        _spam_tasks[user_id].cancel()

    bot = get_bot()
    _spam_messages.setdefault(user_id, [])

    async def spam_loop():
        interval = spam_config.initial_interval_sec
        text_index = 0

        async with async_session() as session:
            await create_log(session, user_id, "spam_started",
                             task_block_id=block_id)
            await session.commit()

        try:
            while True:
                await asyncio.sleep(interval)

                # Проверяем блок ещё активен
                block, info = await _get_block_info(block_id)
                if not block or block.status in ("done", "skipped", "failed"):
                    break

                # Проверяем рабочее время
                user = info["user"]
                tz = ZoneInfo(user.timezone or "Europe/Moscow")
                now = datetime.now(tz)
                current_time = now.time()

                if _is_in_quiet_time(current_time, user.quiet_start, user.quiet_end):
                    break

                # Отправляем спам
                text = SPAM_TEXTS[text_index % len(SPAM_TEXTS)]
                try:
                    msg = await bot.send_message(user_id, text)
                    _spam_messages[user_id].append(msg.message_id)
                except Exception as e:
                    logger.error(f"Ошибка отправки спама user={user_id}: {e}")
                    break

                text_index += 1
                interval = min(
                    interval * spam_config.multiplier,
                    spam_config.max_interval_sec,
                )

        except asyncio.CancelledError:
            pass
        finally:
            async with async_session() as session:
                await create_log(session, user_id, "spam_stopped",
                                 task_block_id=block_id)
                await session.commit()

    task = asyncio.create_task(spam_loop())
    _spam_tasks[user_id] = task


async def stop_spam_and_cleanup(user_id: int) -> None:
    """Останавливает спам и удаляет все спам-сообщения."""
    from backend.bot.scheduler import get_bot

    # Останавливаем спам-таск
    if user_id in _spam_tasks:
        _spam_tasks[user_id].cancel()
        del _spam_tasks[user_id]

    # Удаляем спам-сообщения
    bot = get_bot()
    if user_id in _spam_messages:
        for msg_id in _spam_messages[user_id]:
            try:
                await bot.delete_message(user_id, msg_id)
            except Exception:
                pass  # Сообщение уже удалено или старое
        _spam_messages[user_id].clear()


# === Итог дня ===


async def send_day_summary(user_id: int) -> None:
    """Отправляет итог дня пользователю."""
    from backend.bot.scheduler import get_bot, schedule_day_summary

    bot = get_bot()

    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        tz = ZoneInfo(user.timezone or "Europe/Moscow")
        today = datetime.now(tz).date()

        blocks = await get_blocks_for_day(session, user_id, today)
        categories = await list_categories(session, user_id)
        cat_map = {c.id: c for c in categories}

    if not blocks:
        # Нет блоков — не отправляем
        # Планируем на завтра
        await schedule_day_summary(user_id, user.timezone or "Europe/Moscow")
        return

    # Считаем статистику
    done = sum(1 for b in blocks if b.status == "done")
    partial = sum(1 for b in blocks if b.status == "partial")
    failed = sum(1 for b in blocks if b.status == "failed")
    skipped = sum(1 for b in blocks if b.status == "skipped")

    # Время по категориям
    cat_time: dict[int, dict[str, int]] = {}  # {cat_id: {plan: X, actual: Y}}

    async with async_session() as session:
        for block in blocks:
            cat_id = None
            for tid in set(block.task_ids or []):
                task = await get_task(session, tid, user_id)
                if task:
                    cat_id = task.category_id
                    break
            if cat_id is None:
                continue

            if cat_id not in cat_time:
                cat_time[cat_id] = {"plan": 0, "actual": 0}

            # Плановое время
            if block.duration_type == "fixed":
                plan_min = block.duration_min or 0
            elif block.duration_type == "range":
                plan_min = (block.min_duration_min or 0 + (block.max_duration_min or 0)) // 2
            else:
                plan_min = block.max_duration_min or 60
            cat_time[cat_id]["plan"] += plan_min

            # Фактическое время
            if block.actual_duration_min is not None:
                cat_time[cat_id]["actual"] += block.actual_duration_min
            elif block.status == "done" and block.duration_type == "fixed":
                cat_time[cat_id]["actual"] += block.duration_min or 0

    # Формируем текст
    lines = [
        f"📊 *Итог дня — {today.strftime('%d.%m.%Y')}*\n",
        f"✅ Выполнено: {done} блоков",
        f"⚡ Частично: {partial} блоков",
        f"❌ Провалено: {failed} блоков",
        f"⏭ Пропущено: {skipped} блоков",
        "",
        "📁 *По категориям:*",
    ]

    for cat_id, times in cat_time.items():
        cat = cat_map.get(cat_id)
        if not cat:
            continue
        plan_h, plan_m = divmod(times["plan"], 60)
        act_h, act_m = divmod(times["actual"], 60)
        plan_str = f"{plan_h}ч {plan_m}мин" if plan_h else f"{plan_m}мин"
        act_str = f"{act_h}ч {act_m}мин" if act_h else f"{act_m}мин"
        check = " ✅" if times["actual"] >= times["plan"] and times["plan"] > 0 else ""
        lines.append(f"  {cat.emoji or ''} {cat.name}: {act_str} (план: {plan_str}){check}")

    # Общее фактическое время open/range блоков
    open_actual = sum(
        b.actual_duration_min or 0
        for b in blocks
        if b.duration_type in ("open", "range") and b.actual_duration_min
    )
    if open_actual:
        lines.append(f"\n⏱ Фактическое время открытых блоков: {open_actual} мин")

    text = "\n".join(lines)

    # Кнопка открыть Web App
    from backend.config import settings
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📅 Редактировать план",
            web_app={"url": settings.frontend_url},
        )],
    ])

    await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode="Markdown")

    # Логируем
    async with async_session() as session:
        await create_log(session, user_id, "day_summary", payload={
            "done": done, "partial": partial, "failed": failed, "skipped": skipped,
        })
        await session.commit()

    # Планируем итог на завтра
    await schedule_day_summary(user_id, user.timezone or "Europe/Moscow")


# === Спам для пустых слотов ===


async def send_empty_slots_evening_reminder(user_id: int) -> None:
    """Вечернее напоминание: завтра есть свободные слоты + задачи в бэклоге."""
    from backend.bot.scheduler import get_bot

    bot = get_bot()

    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        tz = ZoneInfo(user.timezone or "Europe/Moscow")
        tomorrow = (datetime.now(tz) + timedelta(days=1)).date()

        from backend.db.crud.blocks import check_empty_slots_and_backlog
        result = await check_empty_slots_and_backlog(session, user_id, tomorrow)

        spam_config = await get_spam_config(session, user_id)

    if not result["should_remind"]:
        # Перепланируем на следующий вечер
        from backend.bot.scheduler import schedule_empty_slots_check
        await schedule_empty_slots_check(user_id, user.timezone or "Europe/Moscow")
        return

    free_h, free_m = divmod(result["free_minutes"], 60)
    free_str = f"{free_h}ч {free_m}мин" if free_h else f"{free_m} мин"

    from backend.config import settings
    text = (
        f"📋 На завтра есть *{free_str}* свободного времени, "
        f"а в бэклоге *{result['unassigned_count']}* нераспределённых задач.\n\n"
        f"Заполни план, чтобы день прошёл продуктивно! 💪"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📅 Открыть планировщик",
            web_app={"url": settings.frontend_url},
        )],
    ])

    await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode="Markdown")

    async with async_session() as session:
        await create_log(session, user_id, "empty_slots_reminder",
                         payload={"type": "evening", "free_min": result["free_minutes"],
                                  "unassigned": result["unassigned_count"]})
        await session.commit()

    # Перепланируем на следующий вечер
    from backend.bot.scheduler import schedule_empty_slots_check
    await schedule_empty_slots_check(user_id, user.timezone or "Europe/Moscow")


async def send_empty_slots_morning_reminder(user_id: int) -> None:
    """Утреннее напоминание: сегодня есть свободные слоты + задачи в бэклоге.

    Повторяется каждые N минут (из spam_config.empty_slots_interval_min),
    пока слоты не будут заполнены или пока не закончится рабочее время.
    """
    from backend.bot.scheduler import get_bot, scheduler, _safe_add_job

    bot = get_bot()

    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        tz = ZoneInfo(user.timezone or "Europe/Moscow")
        now = datetime.now(tz)
        today = now.date()

        from backend.db.crud.blocks import check_empty_slots_and_backlog
        result = await check_empty_slots_and_backlog(session, user_id, today)

        spam_config = await get_spam_config(session, user_id)
        if not spam_config or not spam_config.empty_slots_enabled:
            return

        # Проверяем тихое время
        current_time = now.time()
        if _is_in_quiet_time(current_time, user.quiet_start, user.quiet_end):
            return

        # Проверяем рабочее время
        from backend.db.crud.blocks import get_weekly_schedule
        schedule = await get_weekly_schedule(session, user_id)
        if not _is_in_working_hours(current_time, schedule):
            return

    if not result["should_remind"]:
        return  # Слоты заполнены или нет задач — не спамим

    free_h, free_m = divmod(result["free_minutes"], 60)
    free_str = f"{free_h}ч {free_m}мин" if free_h else f"{free_m} мин"

    from backend.config import settings
    text = (
        f"⏰ Сегодня ещё *{free_str}* без дела, "
        f"а *{result['unassigned_count']}* задач ждут в бэклоге!\n\n"
        f"Распредели задачи по слотам 📅"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📅 Открыть планировщик",
            web_app={"url": settings.frontend_url},
        )],
    ])

    await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode="Markdown")

    async with async_session() as session:
        await create_log(session, user_id, "empty_slots_reminder",
                         payload={"type": "morning", "free_min": result["free_minutes"],
                                  "unassigned": result["unassigned_count"]})
        await session.commit()

    # Планируем повторное напоминание через N минут
    interval = spam_config.empty_slots_interval_min if spam_config else 30
    next_check = now + timedelta(minutes=interval)
    job_id = f"empty_slots_morning_{user_id}"
    _safe_add_job(
        send_empty_slots_morning_reminder,
        run_date=next_check,
        args=[user_id],
        id=job_id,
    )


# === Восстановление при рестарте ===


async def send_restart_active_block_notification(block: TaskBlock) -> None:
    """Уведомление при рестарте: блок был активен, спросить как прошёл."""
    from backend.bot.scheduler import get_bot

    bot = get_bot()
    # Для restart notification у нас нет info — получаем вручную
    _, restart_info = await _get_block_info(block.id)
    header = _block_header(block, restart_info) if restart_info else (block.block_name or "Блок")

    text = (
        f"🔄 Бот перезапустился.\n"
        f"*{header}* — был активен, как прошёл?"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выполнено", callback_data=f"quest_done:{block.id}"),
            InlineKeyboardButton(text="⚡ Частично", callback_data=f"quest_partial:{block.id}"),
            InlineKeyboardButton(text="❌ Не выполнено", callback_data=f"quest_failed:{block.id}"),
        ],
    ])

    await bot.send_message(block.user_id, text, reply_markup=keyboard, parse_mode="Markdown")

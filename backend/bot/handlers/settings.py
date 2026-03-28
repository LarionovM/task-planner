"""Обработчики /settings и /stats."""

import logging
from datetime import date, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from backend.db.database import async_session
from backend.db.crud.users import (
    get_or_create_user,
    update_user_settings,
    get_spam_config,
    update_spam_config,
)
from backend.db.crud.blocks import list_blocks_for_week, get_weekly_goals
from backend.db.crud.tasks import list_categories, get_task, list_tasks
from backend.db.models import AllowedUser

logger = logging.getLogger(__name__)

router = Router()


class SettingsStates(StatesGroup):
    waiting_timezone = State()
    waiting_quiet_start = State()
    waiting_quiet_end = State()
    waiting_day_end_time = State()


# === /settings ===

def settings_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕐 Часовой пояс", callback_data="settings:tz")],
        [InlineKeyboardButton(text="🔇 Тихое время", callback_data="settings:quiet")],
        [InlineKeyboardButton(text="📊 Время итога дня", callback_data="settings:dayend")],
        [InlineKeyboardButton(text="📢 Настройки спама", callback_data="settings:spam")],
    ])


@router.message(Command("settings"))
async def cmd_settings(message: Message, allowed_user: AllowedUser):
    """Настройки пользователя."""
    async with async_session() as session:
        user = await get_or_create_user(session, allowed_user.telegram_id)

    text = (
        "⚙️ *Настройки*\n\n"
        f"🕐 Часовой пояс: `{user.timezone}`\n"
        f"🔇 Тихое время: `{user.quiet_start.strftime('%H:%M')}–{user.quiet_end.strftime('%H:%M')}`\n"
        f"📊 Итог дня в: `{user.day_end_time.strftime('%H:%M')}`\n\n"
        "Что изменить?"
    )
    await message.answer(text, reply_markup=settings_menu_keyboard(), parse_mode="Markdown")


# --- Часовой пояс ---

@router.callback_query(F.data == "settings:tz")
async def settings_tz(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Введите часовой пояс (например: `Europe/Moscow`, `Asia/Tokyo`, `US/Eastern`):",
        reply_markup=ForceReply(selective=True),
        parse_mode="Markdown",
    )
    await state.set_state(SettingsStates.waiting_timezone)
    await callback.answer()


@router.message(SettingsStates.waiting_timezone, ~F.text.startswith("/"))
async def settings_tz_process(message: Message, state: FSMContext, allowed_user: AllowedUser):
    tz = message.text.strip()

    # Простая валидация
    import pytz
    try:
        pytz.timezone(tz)
    except Exception:
        # Если pytz не установлен — примем как есть
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(tz)
        except Exception:
            await message.answer(f"❌ Неизвестный часовой пояс: `{tz}`", parse_mode="Markdown")
            await state.clear()
            return

    async with async_session() as session:
        await update_user_settings(session, allowed_user.telegram_id, timezone=tz)
        await session.commit()

    await message.answer(
        f"✅ Часовой пояс изменён на `{tz}`",
        parse_mode="Markdown",
        reply_markup=settings_menu_keyboard(),
    )
    await state.clear()


# --- Тихое время ---

@router.callback_query(F.data == "settings:quiet")
async def settings_quiet(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Введите начало тихого времени (HH:MM), например `23:00`:",
        reply_markup=ForceReply(selective=True),
        parse_mode="Markdown",
    )
    await state.set_state(SettingsStates.waiting_quiet_start)
    await callback.answer()


@router.message(SettingsStates.waiting_quiet_start, ~F.text.startswith("/"))
async def settings_quiet_start_process(message: Message, state: FSMContext, allowed_user: AllowedUser):
    from datetime import time
    try:
        parts = message.text.strip().split(":")
        t = time(int(parts[0]), int(parts[1]))
    except Exception:
        await message.answer("❌ Формат: HH:MM (например 23:00)")
        return

    async with async_session() as session:
        await update_user_settings(session, allowed_user.telegram_id, quiet_start=t)
        await session.commit()

    await message.answer(
        f"✅ Начало тихого времени: `{t.strftime('%H:%M')}`\n"
        "Теперь введите конец тихого времени (HH:MM), например `08:00`:",
        reply_markup=ForceReply(selective=True),
        parse_mode="Markdown",
    )
    await state.set_state(SettingsStates.waiting_quiet_end)


@router.message(SettingsStates.waiting_quiet_end, ~F.text.startswith("/"))
async def settings_quiet_end_process(message: Message, state: FSMContext, allowed_user: AllowedUser):
    from datetime import time
    try:
        parts = message.text.strip().split(":")
        t = time(int(parts[0]), int(parts[1]))
    except Exception:
        await message.answer("❌ Формат: HH:MM (например 08:00)")
        return

    async with async_session() as session:
        await update_user_settings(session, allowed_user.telegram_id, quiet_end=t)
        await session.commit()

    await message.answer(
        f"✅ Тихое время: до `{t.strftime('%H:%M')}`",
        parse_mode="Markdown",
        reply_markup=settings_menu_keyboard(),
    )
    await state.clear()


# --- Время итога дня ---

@router.callback_query(F.data == "settings:dayend")
async def settings_dayend(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Введите время итога дня (HH:MM), например `23:50`:",
        reply_markup=ForceReply(selective=True),
        parse_mode="Markdown",
    )
    await state.set_state(SettingsStates.waiting_day_end_time)
    await callback.answer()


@router.message(SettingsStates.waiting_day_end_time, ~F.text.startswith("/"))
async def settings_dayend_process(message: Message, state: FSMContext, allowed_user: AllowedUser):
    from datetime import time
    try:
        parts = message.text.strip().split(":")
        t = time(int(parts[0]), int(parts[1]))
    except Exception:
        await message.answer("❌ Формат: HH:MM (например 23:50)")
        return

    async with async_session() as session:
        await update_user_settings(session, allowed_user.telegram_id, day_end_time=t)
        await session.commit()

    await message.answer(
        f"✅ Итог дня будет в `{t.strftime('%H:%M')}`",
        parse_mode="Markdown",
        reply_markup=settings_menu_keyboard(),
    )
    await state.clear()


# --- Настройки спама ---

@router.callback_query(F.data == "settings:spam")
async def settings_spam(callback: CallbackQuery, allowed_user: AllowedUser):
    async with async_session() as session:
        config = await get_spam_config(session, allowed_user.telegram_id)

    status = "✅ Включён" if config.enabled else "❌ Выключен"
    cats = config.spam_category_ids or []
    cats_text = "все категории" if not cats else f"{len(cats)} категорий"

    text = (
        f"📢 *Настройки спама*\n\n"
        f"Статус: {status}\n"
        f"Начальный интервал: `{config.initial_interval_sec}` сек\n"
        f"Множитель: `{config.multiplier}`x\n"
        f"Макс. интервал: `{config.max_interval_sec}` сек\n"
        f"Применяется к: {cats_text}"
    )

    toggle_text = "❌ Выключить спам" if config.enabled else "✅ Включить спам"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data="settings:spam_toggle")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings:back")],
    ])

    await callback.message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "settings:spam_toggle")
async def settings_spam_toggle(callback: CallbackQuery, allowed_user: AllowedUser):
    async with async_session() as session:
        config = await get_spam_config(session, allowed_user.telegram_id)
        new_enabled = not config.enabled
        await update_spam_config(session, allowed_user.telegram_id, enabled=new_enabled)
        await session.commit()

    status = "✅ включён" if new_enabled else "❌ выключен"
    await callback.message.answer(f"Спам теперь {status}")
    await callback.answer()


@router.callback_query(F.data == "settings:back")
async def settings_back(callback: CallbackQuery, allowed_user: AllowedUser):
    async with async_session() as session:
        user = await get_or_create_user(session, allowed_user.telegram_id)

    text = (
        "⚙️ *Настройки*\n\n"
        f"🕐 Часовой пояс: `{user.timezone}`\n"
        f"🔇 Тихое время: `{user.quiet_start.strftime('%H:%M')}–{user.quiet_end.strftime('%H:%M')}`\n"
        f"📊 Итог дня в: `{user.day_end_time.strftime('%H:%M')}`\n\n"
        "Что изменить?"
    )
    await callback.message.answer(text, reply_markup=settings_menu_keyboard(), parse_mode="Markdown")
    await callback.answer()


# === /stats ===

@router.message(Command("stats"))
async def cmd_stats(message: Message, allowed_user: AllowedUser):
    """Статистика за текущую неделю."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Понедельник

    async with async_session() as session:
        blocks = await list_blocks_for_week(session, allowed_user.telegram_id, week_start)
        categories = await list_categories(session, allowed_user.telegram_id)
        goals = await get_weekly_goals(session, allowed_user.telegram_id)

    if not blocks:
        await message.answer(
            "📊 *Статистика за неделю*\n\n"
            "Пока нет запланированных блоков.\n"
            "Создай задачи и распредели их в календаре!",
            parse_mode="Markdown",
        )
        return

    # Считаем по статусам
    done = sum(1 for b in blocks if b.status == "done")
    partial = sum(1 for b in blocks if b.status == "partial")
    failed = sum(1 for b in blocks if b.status == "failed")
    skipped = sum(1 for b in blocks if b.status == "skipped")
    planned = sum(1 for b in blocks if b.status in ("planned", "active"))

    # Считаем время по категориям
    cat_map = {c.id: c for c in categories}
    goals_map = {g.category_id: g.target_hours for g in goals}
    cat_time: dict[int, int] = {}

    async with async_session() as session:
        for block in blocks:
            cat_id = None
            for tid in (block.task_ids or []):
                task = await get_task(session, tid, allowed_user.telegram_id)
                if task:
                    cat_id = task.category_id
                    break
            if cat_id is None:
                continue

            if block.actual_duration_min is not None:
                mins = block.actual_duration_min
            elif block.duration_type == "fixed":
                mins = block.duration_min or 0
            else:
                mins = block.max_duration_min or 60

            cat_time[cat_id] = cat_time.get(cat_id, 0) + mins

    # Формируем текст
    lines = [
        f"📊 *Статистика за неделю* ({week_start.strftime('%d.%m')}–{(week_start + timedelta(days=6)).strftime('%d.%m')})\n",
        f"📋 Запланировано: {planned}",
        f"✅ Выполнено: {done}",
        f"⚡ Частично: {partial}",
        f"❌ Провалено: {failed}",
        f"⏭ Пропущено: {skipped}",
        "",
        "📁 *По категориям:*",
    ]

    for cat in categories:
        mins = cat_time.get(cat.id, 0)
        if mins == 0:
            continue
        hours = mins // 60
        remainder = mins % 60
        time_str = f"{hours}ч {remainder}мин" if hours else f"{remainder}мин"
        target = goals_map.get(cat.id, 0)
        target_str = f" / цель: {target}ч" if target else ""
        check = " ✅" if target and mins >= target * 60 else ""
        lines.append(f"  {cat.emoji or ''} {cat.name}: {time_str}{target_str}{check}")

    await message.answer("\n".join(lines), parse_mode="Markdown")

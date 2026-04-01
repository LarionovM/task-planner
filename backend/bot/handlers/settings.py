"""Обработчик /settings — настройки, пауза, стоп, админка (v1.2.0)."""

import logging
from datetime import datetime, timedelta, date

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from backend.db.database import async_session
from backend.db.crud.users import (
    get_or_create_user,
    update_user_settings,
    get_spam_config,
    update_spam_config,
)
from backend.db.crud.blocks import list_blocks_for_week, get_weekly_goals
from backend.db.crud.tasks import list_categories, get_task
from backend.db.models import AllowedUser
from backend.bot.reminders import stop_spam_and_cleanup
from backend.bot.scheduler import cancel_user_pomodoro_jobs

logger = logging.getLogger(__name__)

router = Router()


# === Главное меню /settings ===


def _settings_main_keyboard(
    is_admin: bool = False,
    is_stopped: bool = False,
    productive_mode: bool = False,
) -> InlineKeyboardMarkup:
    """Основное меню настроек."""
    rows = []

    # Режим продуктивной работы (помодоро-циклы)
    productive_label = "⚡ Режим продуктивности: ВКЛ" if productive_mode else "⚡ Режим продуктивности: ВЫКЛ"
    rows.append([InlineKeyboardButton(text=productive_label, callback_data="set:toggle_productive")])

    # Пауза / Стоп / Возобновить
    if is_stopped:
        rows.append([InlineKeyboardButton(text="▶️ Возобновить напоминания", callback_data="set:resume")])
    else:
        rows.append([
            InlineKeyboardButton(text="⏸ Пауза", callback_data="set:pause"),
            InlineKeyboardButton(text="⏹ Стоп", callback_data="set:stop"),
        ])

    # Спам
    rows.append([InlineKeyboardButton(text="📢 Спам-настройки", callback_data="set:spam")])

    # Админ-панель
    if is_admin:
        rows.append([InlineKeyboardButton(text="🔑 Админ-панель", callback_data="set:admin")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("settings"))
async def cmd_settings(message: Message, allowed_user: AllowedUser):
    """Команда /settings — главное меню настроек."""
    async with async_session() as session:
        user = await get_or_create_user(session, allowed_user.telegram_id)

    is_stopped = getattr(user, 'reminders_stopped', False) or False
    paused_until = getattr(user, 'reminders_paused_until', None)
    productive_mode = getattr(user, 'productive_mode_enabled', False) or False

    status_text = "✅ Активны"
    if is_stopped:
        status_text = "⏹ Остановлены"
    elif paused_until and paused_until > datetime.now():
        status_text = f"⏸ Пауза до {paused_until.strftime('%H:%M')}"

    productive_text = "ВКЛ ⚡" if productive_mode else "ВЫКЛ"

    text = (
        "⚙️ *Настройки*\n\n"
        f"⚡ Режим продуктивности: {productive_text}\n"
        f"🕐 Часовой пояс: `{user.timezone}`\n"
        f"📢 Напоминания: {status_text}\n\n"
        "Остальные настройки — в Web App (кнопка в /start)"
    )

    await message.answer(
        text,
        reply_markup=_settings_main_keyboard(allowed_user.is_admin, is_stopped, productive_mode),
        parse_mode="Markdown",
    )


# === Пауза ===


def _pause_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="15 мин", callback_data="set:pause:15"),
            InlineKeyboardButton(text="30 мин", callback_data="set:pause:30"),
        ],
        [
            InlineKeyboardButton(text="1 час", callback_data="set:pause:60"),
            InlineKeyboardButton(text="2 часа", callback_data="set:pause:120"),
        ],
        [
            InlineKeyboardButton(text="До конца дня", callback_data="set:pause:eod"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="set:back")],
    ])


@router.callback_query(F.data == "set:pause")
async def cb_pause_menu(callback: CallbackQuery, allowed_user: AllowedUser):
    """Показать варианты паузы."""
    await callback.message.edit_text(
        "⏸ *Пауза напоминаний*\nНа сколько поставить на паузу?",
        reply_markup=_pause_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set:pause:"))
async def cb_pause_select(callback: CallbackQuery, allowed_user: AllowedUser):
    """Выбран вариант паузы."""
    option = callback.data.split(":")[2]
    now = datetime.now()

    if option == "eod":
        # До конца дня
        async with async_session() as session:
            user = await get_or_create_user(session, allowed_user.telegram_id)
            day_end = user.day_end_time
            if day_end:
                until = now.replace(hour=day_end.hour, minute=day_end.minute, second=0)
                if until <= now:
                    until += timedelta(days=1)
            else:
                until = now.replace(hour=23, minute=50, second=0)
    else:
        minutes = int(option)
        until = now + timedelta(minutes=minutes)

    async with async_session() as session:
        await update_user_settings(
            session, allowed_user.telegram_id,
            reminders_paused_until=until,
            reminders_stopped=False,
        )
        await session.commit()

    # Останавливаем активный спам и отменяем помодоро-jobs
    await stop_spam_and_cleanup(allowed_user.telegram_id)
    cancel_user_pomodoro_jobs(allowed_user.telegram_id)

    await callback.message.edit_text(
        f"⏸ Напоминания на паузе до *{until.strftime('%H:%M')}*\n"
        f"Зайди в /settings чтобы возобновить раньше.",
        parse_mode="Markdown",
    )
    await callback.answer()


# === Стоп ===


@router.callback_query(F.data == "set:stop")
async def cb_stop(callback: CallbackQuery, allowed_user: AllowedUser):
    """Остановить напоминания."""
    async with async_session() as session:
        await update_user_settings(
            session, allowed_user.telegram_id,
            reminders_stopped=True,
            reminders_paused_until=None,
        )
        await session.commit()

    # Останавливаем активный спам и отменяем помодоро-jobs
    await stop_spam_and_cleanup(allowed_user.telegram_id)
    cancel_user_pomodoro_jobs(allowed_user.telegram_id)

    await callback.message.edit_text(
        "⏹ Напоминания *остановлены*.\n"
        "Зайди в /settings → ▶️ Возобновить, когда будешь готов.",
        parse_mode="Markdown",
    )
    await callback.answer()


# === Возобновить ===


@router.callback_query(F.data == "set:resume")
async def cb_resume(callback: CallbackQuery, allowed_user: AllowedUser):
    """Возобновить напоминания."""
    async with async_session() as session:
        await update_user_settings(
            session, allowed_user.telegram_id,
            reminders_stopped=False,
            reminders_paused_until=None,
        )
        await session.commit()

    await callback.message.edit_text("✅ Напоминания *включены*!", parse_mode="Markdown")
    await callback.answer()


# === Назад к главному меню ===


@router.callback_query(F.data == "set:back")
async def cb_back(callback: CallbackQuery, allowed_user: AllowedUser):
    """Вернуться к главному меню настроек."""
    async with async_session() as session:
        user = await get_or_create_user(session, allowed_user.telegram_id)

    is_stopped = getattr(user, 'reminders_stopped', False) or False
    paused_until = getattr(user, 'reminders_paused_until', None)

    status_text = "✅ Активны"
    if is_stopped:
        status_text = "⏹ Остановлены"
    elif paused_until and paused_until > datetime.now():
        status_text = f"⏸ Пауза до {paused_until.strftime('%H:%M')}"

    productive_mode = getattr(user, 'productive_mode_enabled', False) or False
    productive_text = "ВКЛ ⚡" if productive_mode else "ВЫКЛ"

    text = (
        "⚙️ *Настройки*\n\n"
        f"⚡ Режим продуктивности: {productive_text}\n"
        f"🕐 Часовой пояс: `{user.timezone}`\n"
        f"📢 Напоминания: {status_text}\n\n"
        "Остальные настройки — в Web App (кнопка в /start)"
    )

    await callback.message.edit_text(
        text,
        reply_markup=_settings_main_keyboard(allowed_user.is_admin, is_stopped, productive_mode),
        parse_mode="Markdown",
    )
    await callback.answer()


# === Режим продуктивности ===


@router.callback_query(F.data == "set:toggle_productive")
async def cb_toggle_productive(callback: CallbackQuery, allowed_user: AllowedUser):
    """Переключить режим продуктивной работы (помодоро-циклы)."""
    async with async_session() as session:
        user = await get_or_create_user(session, allowed_user.telegram_id)
        current = getattr(user, 'productive_mode_enabled', False) or False
        new_value = not current
        await update_user_settings(session, allowed_user.telegram_id, productive_mode_enabled=new_value)
        await session.commit()

    if new_value:
        # Включили — запускаем помодоро-цикл на сегодня
        from backend.bot.scheduler import schedule_pomodoro_cycle
        user_tz = user.timezone or "Europe/Moscow"
        await schedule_pomodoro_cycle(allowed_user.telegram_id, user_tz)
        answer_text = "⚡ Режим продуктивности *включён*! Циклы фокуса запланированы."
    else:
        # Выключили — отменяем помодоро-jobs
        cancel_user_pomodoro_jobs(allowed_user.telegram_id)
        answer_text = "⚡ Режим продуктивности *выключен*. Циклы фокуса остановлены."

    is_stopped = getattr(user, 'reminders_stopped', False) or False
    await callback.message.edit_text(
        answer_text,
        reply_markup=_settings_main_keyboard(allowed_user.is_admin, is_stopped, new_value),
        parse_mode="Markdown",
    )
    await callback.answer()


# === Спам-настройки ===


@router.callback_query(F.data == "set:spam")
async def cb_spam(callback: CallbackQuery, allowed_user: AllowedUser):
    """Настройки спама."""
    async with async_session() as session:
        config = await get_spam_config(session, allowed_user.telegram_id)

    status = "✅ Включён" if config.enabled else "❌ Выключен"
    toggle_text = "❌ Выключить" if config.enabled else "✅ Включить"

    text = (
        f"📢 *Спам-настройки*\n\n"
        f"Статус: {status}\n"
        f"Интервал: {config.initial_interval_sec} сек → x{config.multiplier} → макс {config.max_interval_sec} сек\n\n"
        "_Детальная настройка — в Web App_"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data="set:spam_toggle")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="set:back")],
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "set:spam_toggle")
async def cb_spam_toggle(callback: CallbackQuery, allowed_user: AllowedUser):
    """Переключить спам."""
    async with async_session() as session:
        config = await get_spam_config(session, allowed_user.telegram_id)
        new_enabled = not config.enabled
        await update_spam_config(session, allowed_user.telegram_id, enabled=new_enabled)
        await session.commit()

    status = "✅ включён" if new_enabled else "❌ выключен"
    await callback.message.edit_text(f"Спам теперь {status}")
    await callback.answer()


# === Админ-панель (через /settings) ===


@router.callback_query(F.data == "set:admin")
async def cb_admin_panel(callback: CallbackQuery, allowed_user: AllowedUser):
    """Открыть админ-панель (для is_admin=true)."""
    if not allowed_user.is_admin:
        await callback.answer("Нет доступа", show_alert=True)
        return

    # Импортируем админ-функции
    from backend.bot.handlers.admin import admin_keyboard, admin_text
    await callback.message.edit_text(
        admin_text(),
        reply_markup=admin_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer()


# === /stats ===


@router.message(Command("stats"))
async def cmd_stats(message: Message, allowed_user: AllowedUser):
    """Статистика за текущую неделю."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    async with async_session() as session:
        blocks = await list_blocks_for_week(session, allowed_user.telegram_id, week_start)
        categories = await list_categories(session, allowed_user.telegram_id)
        goals = await get_weekly_goals(session, allowed_user.telegram_id)

    if not blocks:
        await message.answer(
            "📊 *Статистика за неделю*\n\n"
            "Пока нет помодоро-сессий.\n"
            "Создай задачи и запусти планировщик!",
            parse_mode="Markdown",
        )
        return

    # Считаем помодоро по статусам
    done = sum(1 for b in blocks if b.status == "done")
    partial = sum(1 for b in blocks if b.status == "partial")
    failed = sum(1 for b in blocks if b.status == "failed")
    skipped = sum(1 for b in blocks if b.status == "skipped")
    planned = sum(1 for b in blocks if b.status in ("planned", "active"))
    total = len(blocks)

    # Время по категориям
    cat_map = {c.id: c for c in categories}
    goals_map = {g.category_id: g.target_hours for g in goals}
    cat_time: dict[int, int] = {}

    async with async_session() as session:
        for block in blocks:
            task_id = getattr(block, 'task_id', None)
            if not task_id:
                # Старые блоки с task_ids
                task_ids = getattr(block, 'task_ids', None)
                if task_ids:
                    task_id = task_ids[0] if task_ids else None

            if not task_id:
                continue

            task = await get_task(session, task_id, allowed_user.telegram_id)
            if not task:
                continue

            mins = block.actual_duration_min or block.duration_min or 25
            cat_time[task.category_id] = cat_time.get(task.category_id, 0) + mins

    lines = [
        f"📊 *Статистика за неделю* ({week_start.strftime('%d.%m')}–{(week_start + timedelta(days=6)).strftime('%d.%m')})\n",
        f"🍅 Всего помодоро: {total}",
        f"✅ Выполнено: {done}",
        f"⚡ Частично: {partial}",
        f"❌ Провалено: {failed}",
        f"⏭ Пропущено: {skipped}",
        f"📋 Осталось: {planned}",
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

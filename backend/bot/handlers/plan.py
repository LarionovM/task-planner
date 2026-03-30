"""Обработчик /plan — план на сегодня/завтра/неделю (v1.2.0)."""

import logging
from datetime import date, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from backend.db.database import async_session
from backend.db.crud.users import get_or_create_user
from backend.db.crud.tasks import get_tasks_for_today, list_tasks
from backend.db.crud.events import get_events_for_day
from backend.db.crud.tasks import list_categories
from backend.db.models import AllowedUser

logger = logging.getLogger(__name__)

router = Router()

# Маппинг статусов на эмодзи
STATUS_EMOJI = {
    "grooming": "🔘",
    "in_progress": "🔵",
    "blocked": "🔴",
    "done": "✅",
}


async def _format_plan_for_day(user_id: int, target_date: date) -> str:
    """Форматирует план на конкретный день."""
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    day_name = day_names[target_date.weekday()]
    date_str = target_date.strftime("%d.%m")

    async with async_session() as session:
        tasks = await get_tasks_for_today(session, user_id, target_date)
        events = await get_events_for_day(session, user_id, target_date)
        categories = await list_categories(session, user_id)

    cat_map = {c.id: c for c in categories}

    lines = [f"📅 *{day_name}, {date_str}*\n"]

    # События с конкретным временем
    if events:
        lines.append("📌 *События:*")
        for e in events:
            start = e.start_time.strftime("%H:%M") if e.start_time else "?"
            end = e.end_time.strftime("%H:%M") if e.end_time else "?"
            cat = cat_map.get(e.category_id)
            cat_str = f" {cat.emoji}" if cat and cat.emoji else ""
            status_mark = "✅" if e.status == "done" else "⬜️"
            lines.append(f"  {status_mark} {start}–{end} {e.name}{cat_str}")
        lines.append("")

    # Задачи на день
    if tasks:
        lines.append("📋 *Задачи:*")
        for t in tasks:
            cat = cat_map.get(t.category_id)
            cat_str = f" {cat.emoji}" if cat and cat.emoji else ""
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.priority, "")
            status_emoji = STATUS_EMOJI.get(t.status, "🔘")
            time_str = f" (~{t.estimated_time_min}м)" if t.estimated_time_min else ""
            lines.append(f"  {status_emoji} {priority_emoji} {t.name}{cat_str}{time_str}")
    elif not events:
        lines.append("_Нет задач и событий на этот день_")

    return "\n".join(lines)


def _plan_navigation_keyboard(current_date: date) -> InlineKeyboardMarkup:
    """Кнопки навигации по дням."""
    today = date.today()
    tomorrow = today + timedelta(days=1)

    rows = []
    if current_date == today:
        rows.append([
            InlineKeyboardButton(text="Завтра →", callback_data=f"plan:{tomorrow.isoformat()}"),
        ])
        rows.append([
            InlineKeyboardButton(text="📅 На неделю", callback_data="plan:week"),
        ])
    elif current_date == tomorrow:
        rows.append([
            InlineKeyboardButton(text="← Сегодня", callback_data=f"plan:{today.isoformat()}"),
            InlineKeyboardButton(text="→", callback_data=f"plan:{(tomorrow + timedelta(days=1)).isoformat()}"),
        ])
    else:
        prev_day = current_date - timedelta(days=1)
        next_day = current_date + timedelta(days=1)
        rows.append([
            InlineKeyboardButton(text="←", callback_data=f"plan:{prev_day.isoformat()}"),
            InlineKeyboardButton(text="→", callback_data=f"plan:{next_day.isoformat()}"),
        ])
        rows.append([
            InlineKeyboardButton(text="📅 Сегодня", callback_data=f"plan:{today.isoformat()}"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("plan"))
async def cmd_plan(message: Message, allowed_user: AllowedUser):
    """Команда /plan — план на сегодня."""
    today = date.today()
    text = await _format_plan_for_day(allowed_user.telegram_id, today)
    keyboard = _plan_navigation_keyboard(today)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data.startswith("plan:"))
async def cb_plan_navigate(callback: CallbackQuery, allowed_user: AllowedUser):
    """Навигация по дням плана."""
    data = callback.data.split(":", 1)[1]

    if data == "week":
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        lines = ["📅 *План на неделю*\n"]

        for i in range(7):
            day = week_start + timedelta(days=i)
            day_text = await _format_plan_for_day(allowed_user.telegram_id, day)
            lines.append(day_text)
            lines.append("")

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 Сегодня", callback_data=f"plan:{today.isoformat()}")],
        ])

        full_text = "\n".join(lines)
        if len(full_text) > 4000:
            full_text = full_text[:4000] + "\n_...обрезано_"

        await callback.message.edit_text(full_text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        target_date = date.fromisoformat(data)
        text = await _format_plan_for_day(allowed_user.telegram_id, target_date)
        keyboard = _plan_navigation_keyboard(target_date)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

    await callback.answer()

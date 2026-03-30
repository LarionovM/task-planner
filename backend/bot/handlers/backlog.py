"""Обработчик /backlog — список задач со сменой статусов (v1.2.0)."""

import logging
from datetime import date

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from backend.db.database import async_session
from backend.db.crud.tasks import list_tasks, get_tasks_for_today, get_task, update_task, list_categories
from backend.db.crud.blocks import create_log
from backend.db.models import AllowedUser

logger = logging.getLogger(__name__)

router = Router()

# Кол-во задач на страницу
PAGE_SIZE = 5

STATUS_EMOJI = {
    "grooming": "🔘",
    "in_progress": "🔵",
    "blocked": "🔴",
    "done": "✅",
}

STATUS_LABELS = {
    "grooming": "Grooming",
    "in_progress": "In Progress",
    "blocked": "Blocked",
    "done": "Done",
}


async def _format_backlog(user_id: int, filter_type: str = "today") -> tuple[str, list]:
    """Форматирует список задач. Возвращает (текст, список задач)."""
    async with async_session() as session:
        if filter_type == "today":
            tasks = await get_tasks_for_today(session, user_id, date.today())
        else:
            tasks = await list_tasks(session, user_id)
            # Исключаем удалённые (уже фильтруется в list_tasks)

        categories = await list_categories(session, user_id)

    cat_map = {c.id: c for c in categories}

    # Группируем по статусам
    groups = {"grooming": [], "in_progress": [], "blocked": [], "done": []}
    for t in tasks:
        status = getattr(t, 'status', 'grooming') or 'grooming'
        if status in groups:
            groups[status].append(t)

    filter_label = "на сегодня" if filter_type == "today" else "все"
    total = len(tasks)
    lines = [f"📋 *Бэклог ({filter_label}, {total})*\n"]

    for status in ["grooming", "in_progress", "blocked", "done"]:
        group = groups[status]
        if not group:
            continue

        emoji = STATUS_EMOJI[status]
        label = STATUS_LABELS[status]

        if status == "done":
            lines.append(f"\n{emoji} *{label}* ({len(group)}): _скрыто_")
        else:
            lines.append(f"\n{emoji} *{label}* ({len(group)}):")
            for t in group:
                cat = cat_map.get(t.category_id)
                cat_str = f" {cat.emoji}" if cat and cat.emoji else ""
                priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.priority, "")
                lines.append(f"  • {priority_emoji} {t.name}{cat_str}")

    if total == 0:
        lines.append("_Нет задач_")

    return "\n".join(lines), tasks


def _backlog_keyboard(filter_type: str = "today", page: int = 0, has_tasks: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура бэклога."""
    rows = []

    # Фильтры
    if filter_type == "today":
        rows.append([
            InlineKeyboardButton(text="📅 На сегодня ✓", callback_data="bl:filter:today:0"),
            InlineKeyboardButton(text="📋 Все", callback_data="bl:filter:all:0"),
        ])
    else:
        rows.append([
            InlineKeyboardButton(text="📅 На сегодня", callback_data="bl:filter:today:0"),
            InlineKeyboardButton(text="📋 Все ✓", callback_data="bl:filter:all:0"),
        ])

    # Кнопка смены статуса
    if has_tasks:
        rows.append([InlineKeyboardButton(text="🔄 Сменить статус", callback_data=f"bl:status:{filter_type}:0")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("backlog"))
async def cmd_backlog(message: Message, allowed_user: AllowedUser):
    """Команда /backlog — список задач."""
    text, tasks = await _format_backlog(allowed_user.telegram_id, "today")
    keyboard = _backlog_keyboard("today", has_tasks=bool(tasks))
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data.startswith("bl:filter:"))
async def cb_backlog_filter(callback: CallbackQuery, allowed_user: AllowedUser):
    """Смена фильтра бэклога."""
    parts = callback.data.split(":")
    filter_type = parts[2]  # today / all

    text, tasks = await _format_backlog(allowed_user.telegram_id, filter_type)
    keyboard = _backlog_keyboard(filter_type, has_tasks=bool(tasks))
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("bl:status:"))
async def cb_backlog_status_list(callback: CallbackQuery, allowed_user: AllowedUser):
    """Показать список задач для смены статуса (с пагинацией)."""
    parts = callback.data.split(":")
    filter_type = parts[2]  # today / all
    page = int(parts[3])

    async with async_session() as session:
        if filter_type == "today":
            tasks = await get_tasks_for_today(session, user_id=allowed_user.telegram_id, today=date.today())
        else:
            tasks = await list_tasks(session, user_id=allowed_user.telegram_id)

    # Исключаем done для смены статуса
    tasks = [t for t in tasks if (getattr(t, 'status', 'grooming') or 'grooming') != "done"]

    if not tasks:
        await callback.answer("Нет задач для смены статуса", show_alert=True)
        return

    # Пагинация
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_tasks = tasks[start:end]
    total_pages = (len(tasks) + PAGE_SIZE - 1) // PAGE_SIZE

    rows = []
    for t in page_tasks:
        emoji = STATUS_EMOJI.get(getattr(t, 'status', 'grooming'), "🔘")
        label = t.name[:30] + "..." if len(t.name) > 30 else t.name
        rows.append([InlineKeyboardButton(
            text=f"{emoji} {label}",
            callback_data=f"bl:pick:{t.id}:{filter_type}",
        )])

    # Пагинация
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="<<", callback_data=f"bl:status:{filter_type}:{page - 1}"))
    if end < len(tasks):
        nav_row.append(InlineKeyboardButton(text=">>", callback_data=f"bl:status:{filter_type}:{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"bl:filter:{filter_type}:0")])

    await callback.message.edit_text(
        f"Выбери задачу (стр. {page + 1}/{total_pages}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bl:pick:"))
async def cb_backlog_pick_task(callback: CallbackQuery, allowed_user: AllowedUser):
    """Выбрана задача — показать кнопки статусов."""
    parts = callback.data.split(":")
    task_id = int(parts[2])
    filter_type = parts[3]

    async with async_session() as session:
        task = await get_task(session, task_id, allowed_user.telegram_id)

    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    current_status = getattr(task, 'status', 'grooming') or 'grooming'
    current_label = STATUS_LABELS.get(current_status, current_status)

    # Формируем текст с описанием и ссылкой если есть
    text_lines = [f"📝 *{task.name}*"]
    text_lines.append(f"Статус: {STATUS_EMOJI[current_status]} {current_label}")

    description = getattr(task, 'description', None)
    link = getattr(task, 'link', None)

    if description:
        text_lines.append(f"\n📄 _{description}_")
    if link:
        text_lines.append(f"🔗 {link}")

    text_lines.append("\nНовый статус:")

    # Кнопки для всех статусов кроме текущего
    rows = []
    for status, label in STATUS_LABELS.items():
        if status == current_status:
            continue
        emoji = STATUS_EMOJI[status]
        rows.append([InlineKeyboardButton(
            text=f"{emoji} {label}",
            callback_data=f"bl:set:{task_id}:{status}:{filter_type}",
        )])

    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"bl:status:{filter_type}:0")])

    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bl:set:"))
async def cb_backlog_set_status(callback: CallbackQuery, allowed_user: AllowedUser):
    """Установить новый статус задаче."""
    parts = callback.data.split(":")
    task_id = int(parts[2])
    new_status = parts[3]
    filter_type = parts[4]

    async with async_session() as session:
        task = await update_task(session, task_id, allowed_user.telegram_id, status=new_status)
        if task:
            await create_log(
                session, allowed_user.telegram_id, "task_status_changed",
                payload={"task_id": task_id, "new_status": new_status, "task_name": task.name},
            )
            await session.commit()

    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    emoji = STATUS_EMOJI.get(new_status, "")
    label = STATUS_LABELS.get(new_status, new_status)

    await callback.message.edit_text(
        f"✅ *{task.name}*\nСтатус изменён на: {emoji} {label}",
        parse_mode="Markdown",
    )
    await callback.answer()

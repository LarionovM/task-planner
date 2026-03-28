"""Обработчики /admin — панель администратора."""

import logging

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
    create_allowed_user,
    delete_allowed_user,
    list_allowed_users,
    toggle_user_active,
    get_or_create_user,
    get_allowed_user,
    resolve_user_input,
)
from backend.db.crud.admin import get_user_stats
from backend.db.models import AllowedUser
from backend.bot.middlewares import _pending_requests

logger = logging.getLogger(__name__)

router = Router()


# === FSM состояния для админ-действий ===

class AdminStates(StatesGroup):
    waiting_add_user_id = State()
    waiting_delete_user_id = State()
    waiting_toggle_user_id = State()
    waiting_stats_user_id = State()


def _user_display(u: AllowedUser) -> str:
    """Форматирует отображение пользователя."""
    if u.username:
        return f"@{u.username}"
    if u.first_name:
        return u.first_name
    return str(u.telegram_id)


# === Главное меню админа ===

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура главного меню админа."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить пользователя", callback_data="admin:add")],
        [InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data="admin:delete")],
        [InlineKeyboardButton(text="🔇 Вкл/выкл пользователя", callback_data="admin:toggle")],
        [InlineKeyboardButton(text="📊 Статистика пользователя", callback_data="admin:stats")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin:list")],
    ])


async def _user_select_keyboard(admin_id: int, action: str) -> InlineKeyboardMarkup:
    """Генерирует кнопки для выбора пользователя из списка."""
    async with async_session() as session:
        users = await list_allowed_users(session)

    buttons = []
    for u in users:
        if u.telegram_id == admin_id:
            continue  # Не показываем самого админа
        status = "✅" if u.is_active else "🔇"
        label = f"{status} {_user_display(u)}"
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"admin_select:{action}:{u.telegram_id}",
        )])

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("admin"))
async def cmd_admin(message: Message, allowed_user: AllowedUser):
    """Команда /admin — панель администратора."""
    if not allowed_user.is_admin:
        await message.answer("🚫 Доступно только администратору.")
        return

    await message.answer(
        "🔑 *Панель администратора*\n\nВыберите действие:",
        reply_markup=admin_menu_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery, state: FSMContext, allowed_user: AllowedUser):
    if not allowed_user.is_admin:
        return
    await state.clear()
    await callback.message.answer(
        "🔑 *Панель администратора*\n\nВыберите действие:",
        reply_markup=admin_menu_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer()


# === Добавление пользователя ===

@router.callback_query(F.data == "admin:add")
async def admin_add_start(callback: CallbackQuery, state: FSMContext, allowed_user: AllowedUser):
    if not allowed_user.is_admin:
        await callback.answer("🚫 Только для админа", show_alert=True)
        return

    await callback.message.answer(
        "Введите *Telegram ID* пользователя для добавления.\n\n"
        "💡 Узнать ID можно у бота @userinfobot\n"
        "После первого сообщения боту его @username появится в списке.",
        reply_markup=ForceReply(selective=True),
        parse_mode="Markdown",
    )
    await state.set_state(AdminStates.waiting_add_user_id)
    await callback.answer()


@router.message(AdminStates.waiting_add_user_id, ~F.text.startswith("/"))
async def admin_add_process(message: Message, state: FSMContext, allowed_user: AllowedUser):
    if not allowed_user.is_admin:
        return

    text = (message.text or "").strip()

    try:
        new_user_id = int(text)
    except ValueError:
        await message.answer(
            "❌ Для добавления нужен числовой Telegram ID.\n"
            "💡 Узнать ID: @userinfobot",
            parse_mode="Markdown",
            reply_markup=admin_menu_keyboard(),
        )
        await state.clear()
        return

    async with async_session() as session:
        existing = await get_allowed_user(session, new_user_id)
        if existing:
            name = _user_display(existing)
            await message.answer(
                f"⚠️ {name} (`{new_user_id}`) уже в списке.",
                parse_mode="Markdown",
            )
            await state.clear()
            return

        await create_allowed_user(
            session,
            telegram_id=new_user_id,
            added_by=allowed_user.telegram_id,
        )
        await get_or_create_user(session, new_user_id)
        await session.commit()

    await message.answer(
        f"✅ Пользователь `{new_user_id}` добавлен!",
        parse_mode="Markdown",
        reply_markup=admin_menu_keyboard(),
    )
    await state.clear()


# === Удаление пользователя ===

@router.callback_query(F.data == "admin:delete")
async def admin_delete_start(callback: CallbackQuery, state: FSMContext, allowed_user: AllowedUser):
    if not allowed_user.is_admin:
        await callback.answer("🚫 Только для админа", show_alert=True)
        return

    keyboard = await _user_select_keyboard(allowed_user.telegram_id, "delete")
    await callback.message.answer(
        "Выберите пользователя или введите *@username* / *ID*:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    await state.set_state(AdminStates.waiting_delete_user_id)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_select:delete:"))
async def admin_delete_select(callback: CallbackQuery, state: FSMContext, allowed_user: AllowedUser):
    if not allowed_user.is_admin:
        return
    target_id = int(callback.data.split(":")[2])
    await _do_delete(callback.message, allowed_user, target_id)
    await state.clear()
    await callback.answer()


@router.message(AdminStates.waiting_delete_user_id, ~F.text.startswith("/"))
async def admin_delete_process(message: Message, state: FSMContext, allowed_user: AllowedUser):
    if not allowed_user.is_admin:
        return

    async with async_session() as session:
        target = await resolve_user_input(session, message.text or "")

    if not target:
        await message.answer(
            "❌ Пользователь не найден.\n"
            "Введите @username или числовой ID.",
            parse_mode="Markdown",
        )
        return

    await _do_delete(message, allowed_user, target.telegram_id)
    await state.clear()


async def _do_delete(message: Message, allowed_user: AllowedUser, target_id: int):
    if target_id == allowed_user.telegram_id:
        await message.answer("❌ Нельзя удалить самого себя!")
        return

    async with async_session() as session:
        target = await get_allowed_user(session, target_id)
        name = _user_display(target) if target else str(target_id)
        deleted = await delete_allowed_user(session, target_id)
        await session.commit()

    if deleted:
        await message.answer(
            f"✅ {name} удалён.",
            parse_mode="Markdown",
            reply_markup=admin_menu_keyboard(),
        )
    else:
        await message.answer("⚠️ Пользователь не найден.", parse_mode="Markdown")


# === Вкл/выкл пользователя ===

@router.callback_query(F.data == "admin:toggle")
async def admin_toggle_start(callback: CallbackQuery, state: FSMContext, allowed_user: AllowedUser):
    if not allowed_user.is_admin:
        await callback.answer("🚫 Только для админа", show_alert=True)
        return

    keyboard = await _user_select_keyboard(allowed_user.telegram_id, "toggle")
    await callback.message.answer(
        "Выберите пользователя или введите *@username* / *ID*:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    await state.set_state(AdminStates.waiting_toggle_user_id)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_select:toggle:"))
async def admin_toggle_select(callback: CallbackQuery, state: FSMContext, allowed_user: AllowedUser):
    if not allowed_user.is_admin:
        return
    target_id = int(callback.data.split(":")[2])
    await _do_toggle(callback.message, target_id)
    await state.clear()
    await callback.answer()


@router.message(AdminStates.waiting_toggle_user_id, ~F.text.startswith("/"))
async def admin_toggle_process(message: Message, state: FSMContext, allowed_user: AllowedUser):
    if not allowed_user.is_admin:
        return

    async with async_session() as session:
        target = await resolve_user_input(session, message.text or "")

    if not target:
        await message.answer("❌ Пользователь не найден.", parse_mode="Markdown")
        return

    await _do_toggle(message, target.telegram_id)
    await state.clear()


async def _do_toggle(message: Message, target_id: int):
    async with async_session() as session:
        user = await toggle_user_active(session, target_id)
        await session.commit()

    if user:
        status = "✅ активен" if user.is_active else "🔇 отключён"
        name = _user_display(user)
        await message.answer(
            f"{name} теперь {status}.",
            parse_mode="Markdown",
            reply_markup=admin_menu_keyboard(),
        )
    else:
        await message.answer("⚠️ Пользователь не найден.", parse_mode="Markdown")


# === Статистика пользователя ===

@router.callback_query(F.data == "admin:stats")
async def admin_stats_start(callback: CallbackQuery, state: FSMContext, allowed_user: AllowedUser):
    if not allowed_user.is_admin:
        await callback.answer("🚫 Только для админа", show_alert=True)
        return

    keyboard = await _user_select_keyboard(allowed_user.telegram_id, "stats")
    await callback.message.answer(
        "Выберите пользователя или введите *@username* / *ID*:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    await state.set_state(AdminStates.waiting_stats_user_id)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_select:stats:"))
async def admin_stats_select(callback: CallbackQuery, state: FSMContext, allowed_user: AllowedUser):
    if not allowed_user.is_admin:
        return
    target_id = int(callback.data.split(":")[2])
    await _do_stats(callback.message, target_id)
    await state.clear()
    await callback.answer()


@router.message(AdminStates.waiting_stats_user_id, ~F.text.startswith("/"))
async def admin_stats_process(message: Message, state: FSMContext, allowed_user: AllowedUser):
    if not allowed_user.is_admin:
        return

    async with async_session() as session:
        target = await resolve_user_input(session, message.text or "")

    if not target:
        await message.answer("❌ Пользователь не найден.", parse_mode="Markdown")
        return

    await _do_stats(message, target.telegram_id)
    await state.clear()


async def _do_stats(message: Message, target_id: int):
    async with async_session() as session:
        target = await get_allowed_user(session, target_id)
        name = _user_display(target) if target else str(target_id)
        stats = await get_user_stats(session, target_id)

    bs = stats["blocks_by_status"]
    text = (
        f"📊 *Статистика* {name}\n"
        f"📅 Неделя: {stats['week_start']}\n\n"
        f"📋 Запланировано: {bs['planned']}\n"
        f"▶️ Активных: {bs['active']}\n"
        f"✅ Выполнено: {bs['done']}\n"
        f"⚡ Частично: 0\n"
        f"❌ Провалено: {bs['failed']}\n"
        f"⏭ Пропущено: {bs['skipped']}\n\n"
        f"⏱ Запланировано: {stats['total_planned_min']} мин\n"
        f"⏱ Фактически: {stats['total_actual_min']} мин"
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=admin_menu_keyboard())


# === Список пользователей ===

@router.callback_query(F.data == "admin:list")
async def admin_list_users(callback: CallbackQuery, allowed_user: AllowedUser):
    if not allowed_user.is_admin:
        await callback.answer("🚫 Только для админа", show_alert=True)
        return

    async with async_session() as session:
        users = await list_allowed_users(session)

    if not users:
        await callback.message.answer("Список пуст.")
        await callback.answer()
        return

    lines = ["👥 *Список пользователей:*\n"]
    for u in users:
        status = "✅" if u.is_active else "🔇"
        admin_badge = " 👑" if u.is_admin else ""
        name = _user_display(u)
        lines.append(f"{status} {name} (`{u.telegram_id}`){admin_badge}")

    await callback.message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=admin_menu_keyboard(),
    )
    await callback.answer()


# === Запросы на доступ ===


@router.callback_query(F.data.startswith("access_request:approve:"))
async def admin_approve_request(callback: CallbackQuery, allowed_user: AllowedUser):
    """Одобрение запроса на доступ."""
    if not allowed_user.is_admin:
        await callback.answer("🚫 Только для админа", show_alert=True)
        return

    target_id = int(callback.data.split(":")[2])

    async with async_session() as session:
        # Проверяем, не добавлен ли уже
        existing = await get_allowed_user(session, target_id)
        if existing:
            await callback.message.edit_text(
                f"⚠️ Пользователь `{target_id}` уже в списке.",
                parse_mode="Markdown",
            )
            _pending_requests.discard(target_id)
            await callback.answer()
            return

        # Добавляем пользователя
        await create_allowed_user(
            session,
            telegram_id=target_id,
            added_by=allowed_user.telegram_id,
        )
        await get_or_create_user(session, target_id)
        await session.commit()

    # Убираем из ожидающих
    _pending_requests.discard(target_id)

    # Обновляем сообщение у админа
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ *Одобрено!*",
        parse_mode="Markdown",
    )

    # Уведомляем пользователя
    try:
        from aiogram.types import WebAppInfo
        from backend.config import settings

        frontend_url = settings.frontend_url
        if frontend_url.startswith("https://"):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📅 Открыть планировщик",
                    web_app=WebAppInfo(url=frontend_url),
                )],
            ])
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📅 Открыть планировщик",
                    url=frontend_url,
                )],
            ])

        await callback.bot.send_message(
            target_id,
            "🎉 *Доступ одобрен!*\n\n"
            "Администратор добавил вас в бота.\n"
            "Нажмите кнопку ниже, чтобы начать планировать!",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {target_id}: {e}")

    await callback.answer("Пользователь добавлен!")


@router.callback_query(F.data.startswith("access_request:reject:"))
async def admin_reject_request(callback: CallbackQuery, allowed_user: AllowedUser):
    """Отклонение запроса на доступ."""
    if not allowed_user.is_admin:
        await callback.answer("🚫 Только для админа", show_alert=True)
        return

    target_id = int(callback.data.split(":")[2])

    # Убираем из ожидающих
    _pending_requests.discard(target_id)

    # Обновляем сообщение у админа
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ *Отклонено*",
        parse_mode="Markdown",
    )

    # Уведомляем пользователя
    try:
        await callback.bot.send_message(
            target_id,
            "😔 *Запрос отклонён*\n\n"
            "Администратор отклонил ваш запрос на доступ.\n"
            "Вы можете связаться с ним напрямую.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {target_id}: {e}")

    await callback.answer("Запрос отклонён")

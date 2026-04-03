"""Middleware для проверки whitelist в aiogram."""

import logging
import time as _time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    TelegramObject,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from backend.config import settings
from backend.db.database import async_session
from backend.db.crud.users import get_allowed_user, create_allowed_user, get_or_create_user

logger = logging.getLogger(__name__)

# Сообщение для пользователей не из whitelist
REJECT_MESSAGE = (
    "🚫 *Бот недоступен*\n\n"
    "Вы не в списке пользователей.\n"
    "Нажмите кнопку ниже, чтобы отправить запрос администратору."
)

# Сообщение если запрос уже отправлен
ALREADY_REQUESTED_MESSAGE = (
    "📩 Запрос уже отправлен.\n"
    "Ожидайте решения администратора."
)

# Хранилище отправленных запросов (telegram_id → True)
# В памяти — сбрасывается при перезагрузке, это нормально
_pending_requests: set[int] = set()

# Кэш whitelist: {telegram_id: (AllowedUser, timestamp)}
# TTL 60 секунд — после этого перечитаем из БД
_whitelist_cache: dict[int, tuple[Any, float]] = {}
_CACHE_TTL = 60  # секунд


def invalidate_whitelist_cache(telegram_id: int | None = None) -> None:
    """Сбросить кэш whitelist (при добавлении/удалении пользователя)."""
    if telegram_id:
        _whitelist_cache.pop(telegram_id, None)
    else:
        _whitelist_cache.clear()


def _request_keyboard() -> InlineKeyboardMarkup:
    """Кнопка отправки запроса доступа."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📩 Отправить запрос",
            callback_data="access_request:send",
        )],
    ])


class WhitelistMiddleware(BaseMiddleware):
    """Проверяет что пользователь в белом списке перед обработкой."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Определяем user_id из события
        user_id = None
        from_user = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
            from_user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id
            from_user = event.from_user

        if user_id is None:
            return  # Игнорируем события без пользователя

        # Проверяем whitelist (с кэшем)
        now = _time.monotonic()
        cached = _whitelist_cache.get(user_id)
        if cached and (now - cached[1]) < _CACHE_TTL:
            allowed = cached[0]
        else:
            async with async_session() as session:
                allowed = await get_allowed_user(session, user_id)
            _whitelist_cache[user_id] = (allowed, now)

        if allowed is None or not allowed.is_active:
            # --- Обработка запроса доступа от неавторизованного пользователя ---
            if isinstance(event, CallbackQuery) and event.data == "access_request:send":
                await self._handle_access_request(event, data)
                return

            # Отправляем сообщение об отказе с кнопкой запроса
            if isinstance(event, Message):
                if user_id in _pending_requests:
                    await event.answer(ALREADY_REQUESTED_MESSAGE, parse_mode="Markdown")
                else:
                    await event.answer(
                        REJECT_MESSAGE,
                        reply_markup=_request_keyboard(),
                        parse_mode="Markdown",
                    )
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Бот недоступен", show_alert=True)
            return  # Не передаём дальше

        # Обновляем username/first_name если изменились
        if from_user:
            changed = False
            if from_user.username and allowed.username != from_user.username:
                allowed.username = from_user.username
                changed = True
            if from_user.first_name and allowed.first_name != from_user.first_name:
                allowed.first_name = from_user.first_name
                changed = True
            if changed:
                async with async_session() as session:
                    from sqlalchemy import update as sql_update
                    from backend.db.models import AllowedUser as AU
                    await session.execute(
                        sql_update(AU)
                        .where(AU.telegram_id == allowed.telegram_id)
                        .values(username=allowed.username, first_name=allowed.first_name)
                    )
                    await session.commit()

        # Сохраняем allowed_user в data для использования в handlers
        data["allowed_user"] = allowed
        return await handler(event, data)

    async def _handle_access_request(
        self, callback: CallbackQuery, data: Dict[str, Any]
    ) -> None:
        """Обработка нажатия кнопки «Отправить запрос»."""
        user = callback.from_user
        user_id = user.id

        # Проверяем не отправлялся ли уже запрос
        if user_id in _pending_requests:
            await callback.answer("📩 Запрос уже отправлен!", show_alert=True)
            return

        # Отмечаем как отправленный
        _pending_requests.add(user_id)

        # Формируем информацию о пользователе
        name_parts = []
        if user.first_name:
            name_parts.append(user.first_name)
        if user.last_name:
            name_parts.append(user.last_name)
        display_name = " ".join(name_parts) if name_parts else "Неизвестный"

        username_str = f"@{user.username}" if user.username else "нет"

        # Отправляем запрос админу
        bot: Bot = data["bot"]
        admin_id = settings.admin_user_id

        admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить",
                    callback_data=f"access_request:approve:{user_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"access_request:reject:{user_id}",
                ),
            ],
        ])

        try:
            await bot.send_message(
                admin_id,
                f"📩 <b>Запрос на доступ</b>\n\n"
                f"👤 Имя: {display_name}\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"📎 Username: {username_str}\n\n"
                f"Одобрить доступ?",
                reply_markup=admin_keyboard,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Не удалось отправить запрос админу: {e}")
            _pending_requests.discard(user_id)
            await callback.answer(
                "❌ Не удалось отправить запрос. Попробуйте позже.",
                show_alert=True,
            )
            return

        # Подтверждаем пользователю
        await callback.message.edit_text(
            "✅ *Запрос отправлен!*\n\n"
            "Администратор получил ваш запрос.\n"
            "Вам придёт уведомление, когда он будет рассмотрен.",
            parse_mode="Markdown",
        )
        await callback.answer()
        logger.info(f"Запрос доступа от {user_id} ({display_name}) отправлен админу")

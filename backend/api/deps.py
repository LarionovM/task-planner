"""Зависимости FastAPI — авторизация и проверка whitelist."""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.crud.users import get_allowed_user, get_or_create_user
from backend.db.models import AllowedUser, User


async def get_current_user(
    x_telegram_user_id: int = Header(..., alias="X-Telegram-User-Id"),
    session: AsyncSession = Depends(get_db),
) -> AllowedUser:
    """Проверяет что пользователь в whitelist и активен."""
    allowed = await get_allowed_user(session, x_telegram_user_id)

    if allowed is None:
        raise HTTPException(
            status_code=403,
            detail="Бот недоступен. Обратитесь к администратору.",
        )

    if not allowed.is_active:
        raise HTTPException(
            status_code=403,
            detail="Ваш аккаунт деактивирован. Обратитесь к администратору.",
        )

    # Создаём настройки если первый вход
    await get_or_create_user(session, x_telegram_user_id)

    return allowed


async def require_admin(
    user: AllowedUser = Depends(get_current_user),
) -> AllowedUser:
    """Проверяет что пользователь — администратор."""
    if not user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Доступно только администратору.",
        )
    return user

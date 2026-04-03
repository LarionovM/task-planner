"""CRUD операции для пользователей и whitelist."""

import logging
from datetime import time

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import DEFAULT_CATEGORIES, DEFAULT_SCHEDULE, settings
from backend.db.models import (
    AllowedUser,
    Category,
    SpamConfig,
    User,
    WeeklySchedule,
)

logger = logging.getLogger(__name__)


async def get_allowed_user(
    session: AsyncSession, telegram_id: int
) -> AllowedUser | None:
    """Проверка пользователя в белом списке."""
    result = await session.execute(
        select(AllowedUser).where(AllowedUser.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_allowed_user_by_username(
    session: AsyncSession, username: str
) -> AllowedUser | None:
    """Поиск пользователя по username (без @)."""
    username = username.lstrip("@").strip()
    result = await session.execute(
        select(AllowedUser).where(AllowedUser.username == username)
    )
    return result.scalar_one_or_none()


async def resolve_user_input(
    session: AsyncSession, text: str
) -> AllowedUser | None:
    """Найти пользователя по ID или username (с/без @)."""
    text = text.strip()
    # Попробуем как число (telegram_id)
    try:
        tid = int(text)
        return await get_allowed_user(session, tid)
    except ValueError:
        pass
    # Попробуем как username
    return await get_allowed_user_by_username(session, text)


async def create_allowed_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
    is_admin: bool = False,
    added_by: int | None = None,
) -> AllowedUser:
    """Добавить пользователя в белый список."""
    user = AllowedUser(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        is_admin=is_admin,
        added_by=added_by,
    )
    session.add(user)
    await session.flush()
    logger.info(f"Пользователь {telegram_id} добавлен в whitelist")
    return user


async def get_or_create_user(
    session: AsyncSession, telegram_id: int
) -> User:
    """Получить или создать настройки пользователя с дефолтами."""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if user is not None:
        return user

    # Создаём настройки пользователя
    user = User(
        telegram_id=telegram_id,
        timezone=settings.default_timezone,
        day_start_time=time(8, 0),
        day_end_time=time(23, 50),
    )
    session.add(user)
    await session.flush()

    # Создаём дефолтные категории
    for i, cat_data in enumerate(DEFAULT_CATEGORIES):
        cat = Category(
            name=cat_data["name"],
            emoji=cat_data["emoji"],
            color=cat_data["color"],
            user_id=telegram_id,
            sort_order=i,
        )
        session.add(cat)

    # Создаём дефолтное расписание недели
    for day_data in DEFAULT_SCHEDULE:
        h_from, m_from = map(int, day_data["active_from"].split(":"))
        h_to, m_to = map(int, day_data["active_to"].split(":"))
        schedule = WeeklySchedule(
            user_id=telegram_id,
            day_of_week=day_data["day_of_week"],
            is_day_off=day_data["is_day_off"],
            active_from=time(h_from, m_from),
            active_to=time(h_to, m_to),
        )
        session.add(schedule)

    # Создаём дефолтный spam_config
    spam = SpamConfig(user_id=telegram_id)
    session.add(spam)

    await session.flush()
    logger.info(f"Пользователь {telegram_id}: созданы настройки и дефолты")
    return user


async def update_user_settings(
    session: AsyncSession,
    telegram_id: int,
    **kwargs,
) -> User:
    """Обновить настройки пользователя (timezone, quiet_start и т.д.)."""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one()

    for key, value in kwargs.items():
        if hasattr(user, key) and value is not None:
            setattr(user, key, value)

    await session.flush()
    return user


async def list_allowed_users(session: AsyncSession) -> list[AllowedUser]:
    """Список всех пользователей в whitelist."""
    result = await session.execute(
        select(AllowedUser).order_by(AllowedUser.added_at)
    )
    return list(result.scalars().all())


async def toggle_user_active(
    session: AsyncSession, telegram_id: int
) -> AllowedUser | None:
    """Переключить is_active пользователя."""
    user = await get_allowed_user(session, telegram_id)
    if user is None:
        return None
    user.is_active = not user.is_active
    await session.flush()
    return user


async def delete_allowed_user(
    session: AsyncSession, telegram_id: int
) -> bool:
    """Удалить пользователя из whitelist вместе со всеми его данными."""
    user = await get_allowed_user(session, telegram_id)
    if user is None:
        return False

    # Удаляем в правильном порядке через raw SQL, т.к. async SQLAlchemy
    # не загружает дочерние записи автоматически (нет lazy load).
    # logs → task_blocks → tasks → weekly_goals → weekly_schedule →
    # spam_config → categories → users → allowed_users
    user_id_tables = [
        "logs", "task_blocks", "tasks", "weekly_goals",
        "weekly_schedule", "spam_config", "categories",
    ]
    for table in user_id_tables:
        await session.execute(
            text(f"DELETE FROM {table} WHERE user_id = :tid"),
            {"tid": telegram_id},
        )

    await session.execute(
        text("DELETE FROM users WHERE telegram_id = :tid"),
        {"tid": telegram_id},
    )
    await session.execute(
        text("DELETE FROM allowed_users WHERE telegram_id = :tid"),
        {"tid": telegram_id},
    )
    await session.flush()
    logger.info(f"Пользователь {telegram_id} удалён из whitelist")
    return True


async def get_spam_config(
    session: AsyncSession, telegram_id: int
) -> SpamConfig | None:
    """Получить настройки спама пользователя."""
    result = await session.execute(
        select(SpamConfig).where(SpamConfig.user_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def update_spam_config(
    session: AsyncSession, telegram_id: int, **kwargs
) -> SpamConfig:
    """Обновить настройки спама."""
    result = await session.execute(
        select(SpamConfig).where(SpamConfig.user_id == telegram_id)
    )
    config = result.scalar_one()
    for key, value in kwargs.items():
        if hasattr(config, key) and value is not None:
            setattr(config, key, value)
    await session.flush()
    return config


async def get_all_active_users(session: AsyncSession) -> list[User]:
    """Все активные пользователи с настройками (для восстановления scheduler)."""
    result = await session.execute(
        select(User).join(AllowedUser, User.telegram_id == AllowedUser.telegram_id)
        .where(AllowedUser.is_active == True)
    )
    return list(result.scalars().all())


async def ensure_admin_exists(session: AsyncSession) -> None:
    """Создать админа из ADMIN_USER_ID при первом запуске."""
    if settings.admin_user_id == 0:
        logger.warning("ADMIN_USER_ID не задан в .env")
        return

    existing = await get_allowed_user(session, settings.admin_user_id)
    if existing is None:
        await create_allowed_user(
            session,
            telegram_id=settings.admin_user_id,
            is_admin=True,
        )
        await get_or_create_user(session, settings.admin_user_id)
        logger.info(f"Админ {settings.admin_user_id} создан")

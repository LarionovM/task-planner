"""Инициализация базы данных — async engine и sessionmaker."""

import os
import logging

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event

from backend.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""
    pass


# Создаём директорию для БД если нет
db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
db_dir = os.path.dirname(db_path)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    # SQLite: один коннект, WAL mode для надёжности
    pool_size=0,  # StaticPool для aiosqlite
    connect_args={"check_same_thread": False},
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    """Включаем WAL mode и foreign keys для SQLite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async def init_db() -> None:
    """Создаёт все таблицы в БД и применяет миграции."""
    # Импорт моделей чтобы они зарегистрировались в metadata
    import backend.db.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Миграции — добавляем новые колонки если их нет
    async with engine.begin() as conn:
        migrations = [
            "ALTER TABLE tasks ADD COLUMN is_epic BOOLEAN DEFAULT 0",
            "ALTER TABLE tasks ADD COLUMN epic_id INTEGER REFERENCES tasks(id)",
            "ALTER TABLE users ADD COLUMN day_start_time TIME DEFAULT '08:00'",
            "ALTER TABLE tasks ADD COLUMN preferred_time TIME",
            "ALTER TABLE tasks ADD COLUMN allow_multi_per_block BOOLEAN DEFAULT 0",
            "ALTER TABLE tasks ADD COLUMN epic_emoji TEXT",
            "ALTER TABLE tasks ADD COLUMN device_type TEXT DEFAULT 'other'",
            "ALTER TABLE spam_config ADD COLUMN empty_slots_enabled BOOLEAN DEFAULT 1",
            "ALTER TABLE spam_config ADD COLUMN empty_slots_interval_min INTEGER DEFAULT 30",
        ]
        for sql in migrations:
            try:
                await conn.execute(__import__("sqlalchemy").text(sql))
                logger.info(f"Миграция: {sql}")
            except Exception:
                pass  # Колонка уже существует

    logger.info("База данных инициализирована")


async def get_db():
    """Dependency для FastAPI — возвращает async сессию."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

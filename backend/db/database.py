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
    from sqlalchemy import text

    async with engine.begin() as conn:
        migrations = [
            # Старые миграции (v1.0 → v1.1)
            "ALTER TABLE tasks ADD COLUMN is_epic BOOLEAN DEFAULT 0",
            "ALTER TABLE tasks ADD COLUMN epic_id INTEGER REFERENCES tasks(id)",
            "ALTER TABLE users ADD COLUMN day_start_time TIME DEFAULT '08:00'",
            "ALTER TABLE tasks ADD COLUMN preferred_time TIME",
            "ALTER TABLE tasks ADD COLUMN allow_multi_per_block BOOLEAN DEFAULT 0",
            "ALTER TABLE tasks ADD COLUMN epic_emoji TEXT",
            "ALTER TABLE tasks ADD COLUMN device_type TEXT DEFAULT 'other'",
            "ALTER TABLE spam_config ADD COLUMN empty_slots_enabled BOOLEAN DEFAULT 1",
            "ALTER TABLE spam_config ADD COLUMN empty_slots_interval_min INTEGER DEFAULT 30",

            # === v1.2.0 — помодоро-центричная переработка ===

            # User: настройки помодоро
            "ALTER TABLE users ADD COLUMN pomodoro_work_min INTEGER DEFAULT 25",
            "ALTER TABLE users ADD COLUMN pomodoro_short_break_min INTEGER DEFAULT 5",
            "ALTER TABLE users ADD COLUMN pomodoro_long_break_min INTEGER DEFAULT 30",
            "ALTER TABLE users ADD COLUMN pomodoro_cycles_before_long INTEGER DEFAULT 4",
            "ALTER TABLE users ADD COLUMN reminders_paused_until DATETIME",
            "ALTER TABLE users ADD COLUMN reminders_stopped BOOLEAN DEFAULT 0",

            # Task: новый статус + назначенная дата
            "ALTER TABLE tasks ADD COLUMN status TEXT DEFAULT 'grooming'",
            "ALTER TABLE tasks ADD COLUMN scheduled_date DATE",

            # Task: описание и ссылка (v1.2.0)
            "ALTER TABLE tasks ADD COLUMN description TEXT",
            "ALTER TABLE tasks ADD COLUMN link TEXT",

            # TaskBlock: помодоро-сессия (task_id вместо task_ids)
            "ALTER TABLE task_blocks ADD COLUMN task_id INTEGER REFERENCES tasks(id)",
            "ALTER TABLE task_blocks ADD COLUMN pomodoro_number INTEGER DEFAULT 1",

            # Tasks: spam_enabled (мог отсутствовать в ранних версиях)
            "ALTER TABLE tasks ADD COLUMN spam_enabled BOOLEAN DEFAULT 1",


            # Таблица уведомлений о версиях (v1.2.0)
            """CREATE TABLE IF NOT EXISTS version_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(telegram_id),
                version VARCHAR(20) NOT NULL,
                sent_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS ix_version_notifications_user_id ON version_notifications(user_id)",
        ]
        for sql in migrations:
            try:
                await conn.execute(text(sql))
                logger.info(f"Миграция: {sql}")
            except Exception:
                pass  # Колонка уже существует / не нужна

        # === v1.5.1 — удаляем устаревшие колонки (SQLite 3.35+) ===
        # Эти колонки были в старых версиях модели, потом убраны из кода,
        # но остались в БД как NOT NULL — что ломало INSERT.
        drop_columns = [
            "ALTER TABLE tasks DROP COLUMN preferred_time",
            "ALTER TABLE tasks DROP COLUMN allow_multi_per_block",
            "ALTER TABLE tasks DROP COLUMN device_type",
            "ALTER TABLE spam_config DROP COLUMN empty_slots_enabled",
            "ALTER TABLE spam_config DROP COLUMN empty_slots_interval_min",
        ]
        for sql in drop_columns:
            try:
                await conn.execute(text(sql))
                logger.info(f"Миграция (drop): {sql}")
            except Exception:
                pass  # Уже удалена / SQLite < 3.35 / колонки не существует

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

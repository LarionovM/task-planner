"""CRUD операции для событий (v1.2.0)."""

import logging
from datetime import date, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Event

logger = logging.getLogger(__name__)


async def list_events(
    session: AsyncSession,
    user_id: int,
    day: date | None = None,
    week_start: date | None = None,
    week_end: date | None = None,
) -> list[Event]:
    """Список событий с фильтрами по дате."""
    query = select(Event).where(Event.user_id == user_id)

    if day is not None:
        query = query.where(Event.day == day)
    elif week_start is not None and week_end is not None:
        query = query.where(Event.day >= week_start, Event.day <= week_end)

    query = query.order_by(Event.day, Event.start_time)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_event(
    session: AsyncSession, event_id: int, user_id: int
) -> Event | None:
    """Получить событие по ID."""
    result = await session.execute(
        select(Event).where(
            Event.id == event_id,
            Event.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def create_event(
    session: AsyncSession, user_id: int, **kwargs
) -> Event:
    """Создать событие."""
    # Конвертация строк HH:MM в time
    if isinstance(kwargs.get("start_time"), str):
        parts = kwargs["start_time"].split(":")
        kwargs["start_time"] = time(int(parts[0]), int(parts[1]))
    if isinstance(kwargs.get("end_time"), str):
        parts = kwargs["end_time"].split(":")
        kwargs["end_time"] = time(int(parts[0]), int(parts[1]))

    event = Event(user_id=user_id, **kwargs)
    session.add(event)
    await session.flush()
    return event


async def update_event(
    session: AsyncSession, event_id: int, user_id: int, **kwargs
) -> Event | None:
    """Обновить событие."""
    event = await get_event(session, event_id, user_id)
    if event is None:
        return None

    # Конвертация строк HH:MM в time
    if isinstance(kwargs.get("start_time"), str):
        parts = kwargs["start_time"].split(":")
        kwargs["start_time"] = time(int(parts[0]), int(parts[1]))
    if isinstance(kwargs.get("end_time"), str):
        parts = kwargs["end_time"].split(":")
        kwargs["end_time"] = time(int(parts[0]), int(parts[1]))

    for key, value in kwargs.items():
        if hasattr(event, key):
            setattr(event, key, value)

    await session.flush()
    return event


async def delete_event(
    session: AsyncSession, event_id: int, user_id: int
) -> bool:
    """Удалить событие."""
    event = await get_event(session, event_id, user_id)
    if event is None:
        return False

    await session.delete(event)
    await session.flush()
    return True


async def get_events_for_day(
    session: AsyncSession,
    user_id: int,
    day: date,
) -> list[Event]:
    """Получить все события на конкретный день (для помодоро-scheduler)."""
    result = await session.execute(
        select(Event).where(
            Event.user_id == user_id,
            Event.day == day,
            Event.status != "skipped",
        ).order_by(Event.start_time)
    )
    return list(result.scalars().all())

"""API маршруты для событий в календаре (v1.2.0)."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.api.schemas import (
    EventCreate,
    EventUpdate,
    EventResponse,
)
from backend.db.database import get_db
from backend.db.crud.events import (
    list_events,
    get_event,
    create_event,
    update_event,
    delete_event,
)
from backend.db.crud.users import get_or_create_user
from backend.db.models import AllowedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[EventResponse])
async def get_events(
    day: str | None = Query(None),  # YYYY-MM-DD
    week_start: str | None = Query(None),
    week_end: str | None = Query(None),
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Список событий с фильтрами по дате."""
    d = date.fromisoformat(day) if day else None
    ws = date.fromisoformat(week_start) if week_start else None
    we = date.fromisoformat(week_end) if week_end else None

    events = await list_events(
        session,
        user_id=allowed.telegram_id,
        day=d,
        week_start=ws,
        week_end=we,
    )
    return [EventResponse.model_validate(e) for e in events]


@router.get("/{event_id}", response_model=EventResponse)
async def get_event_by_id(
    event_id: int,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Получить событие по ID."""
    event = await get_event(session, event_id, allowed.telegram_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    return EventResponse.model_validate(event)


@router.post("", response_model=EventResponse, status_code=201)
async def post_event(
    data: EventCreate,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Создать событие."""
    event = await create_event(
        session,
        user_id=allowed.telegram_id,
        **data.model_dump(),
    )

    # Планируем jobs для напоминаний о событии
    try:
        from backend.db.database import async_session
        async with async_session() as s:
            user = await get_or_create_user(s, allowed.telegram_id)
        from backend.bot.scheduler import schedule_event_jobs
        await schedule_event_jobs(event, user.timezone or "Europe/Moscow")
        logger.info(f"Event jobs scheduled for event={event.id} '{event.name}'")
    except Exception as e:
        logger.error(f"Failed to schedule event jobs: {e}")

    return EventResponse.model_validate(event)


@router.patch("/{event_id}", response_model=EventResponse)
async def patch_event(
    event_id: int,
    data: EventUpdate,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Обновить событие."""
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    event = await update_event(session, event_id, allowed.telegram_id, **kwargs)
    if event is None:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    return EventResponse.model_validate(event)


@router.delete("/{event_id}")
async def delete_event_route(
    event_id: int,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Удалить событие."""
    deleted = await delete_event(session, event_id, allowed.telegram_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    return {"deleted": True}

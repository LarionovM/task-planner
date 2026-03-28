"""API маршруты для расписания недели."""

from datetime import time

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.api.schemas import (
    WeeklyScheduleItem,
    WeeklyScheduleUpdate,
    WeeklyScheduleResponse,
)
from backend.db.database import get_db
from backend.db.crud.blocks import get_weekly_schedule, upsert_weekly_schedule
from backend.db.models import AllowedUser

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


def _time_to_str(t: time) -> str:
    return t.strftime("%H:%M")


def _str_to_time(s: str) -> time:
    parts = s.split(":")
    return time(int(parts[0]), int(parts[1]))


@router.get("", response_model=list[WeeklyScheduleResponse])
async def get_schedule(
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Получить расписание недели."""
    schedule = await get_weekly_schedule(session, allowed.telegram_id)
    return [
        WeeklyScheduleResponse(
            day_of_week=s.day_of_week,
            is_day_off=s.is_day_off,
            active_from=_time_to_str(s.active_from),
            active_to=_time_to_str(s.active_to),
        )
        for s in schedule
    ]


@router.put("", response_model=list[WeeklyScheduleResponse])
async def put_schedule(
    data: WeeklyScheduleUpdate,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Обновить расписание всех 7 дней."""
    days = []
    for item in data.days:
        days.append({
            "day_of_week": item.day_of_week,
            "is_day_off": item.is_day_off,
            "active_from": _str_to_time(item.active_from),
            "active_to": _str_to_time(item.active_to),
        })

    schedule = await upsert_weekly_schedule(session, allowed.telegram_id, days)
    return [
        WeeklyScheduleResponse(
            day_of_week=s.day_of_week,
            is_day_off=s.is_day_off,
            active_from=_time_to_str(s.active_from),
            active_to=_time_to_str(s.active_to),
        )
        for s in schedule
    ]


@router.post("/copy")
async def copy_day_schedule(
    source_day: int,
    target_days: list[int],
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Скопировать расписание одного дня на другие."""
    schedule = await get_weekly_schedule(session, allowed.telegram_id)
    schedule_map = {s.day_of_week: s for s in schedule}

    source = schedule_map.get(source_day)
    if source is None:
        return {"ok": False, "message": "День-источник не найден"}

    # Обновляем целевые дни
    days = []
    for s in schedule:
        if s.day_of_week in target_days:
            days.append({
                "day_of_week": s.day_of_week,
                "is_day_off": source.is_day_off,
                "active_from": source.active_from,
                "active_to": source.active_to,
            })
        else:
            days.append({
                "day_of_week": s.day_of_week,
                "is_day_off": s.is_day_off,
                "active_from": s.active_from,
                "active_to": s.active_to,
            })

    await upsert_weekly_schedule(session, allowed.telegram_id, days)
    return {"ok": True, "copied_to": target_days}

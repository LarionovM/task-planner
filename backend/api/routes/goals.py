"""API маршруты для целей по категориям."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.api.schemas import (
    WeeklyGoalItem,
    WeeklyGoalsUpdate,
    WeeklyGoalResponse,
)
from backend.db.database import get_db
from backend.db.crud.blocks import get_weekly_goals, upsert_weekly_goals
from backend.db.models import AllowedUser

router = APIRouter(prefix="/api/goals", tags=["goals"])


@router.get("", response_model=list[WeeklyGoalResponse])
async def get_goals(
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Получить цели на неделю по категориям."""
    goals = await get_weekly_goals(session, allowed.telegram_id)
    return [
        WeeklyGoalResponse(
            category_id=g.category_id,
            target_hours=g.target_hours,
        )
        for g in goals
    ]


@router.put("", response_model=list[WeeklyGoalResponse])
async def put_goals(
    data: WeeklyGoalsUpdate,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Обновить цели на неделю."""
    goals_data = [
        {"category_id": g.category_id, "target_hours": g.target_hours}
        for g in data.goals
    ]
    goals = await upsert_weekly_goals(session, allowed.telegram_id, goals_data)
    return [
        WeeklyGoalResponse(
            category_id=g.category_id,
            target_hours=g.target_hours,
        )
        for g in goals
    ]

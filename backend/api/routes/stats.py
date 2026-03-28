"""API маршруты для статистики."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, require_admin
from backend.api.schemas import (
    WeekStatsResponse,
    CategoryStatsItem,
)
from backend.db.database import get_db
from backend.db.crud.blocks import (
    list_blocks_for_week,
    get_weekly_schedule,
    get_weekly_goals,
)
from backend.db.crud.tasks import list_categories, get_task
from backend.db.crud.admin import get_user_stats
from backend.db.models import AllowedUser

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/week", response_model=WeekStatsResponse)
async def get_week_stats(
    week_start: date = Query(..., description="Начало недели (понедельник)"),
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Статистика за неделю."""
    blocks = await list_blocks_for_week(session, allowed.telegram_id, week_start)
    categories = await list_categories(session, allowed.telegram_id)
    goals = await get_weekly_goals(session, allowed.telegram_id)
    schedule = await get_weekly_schedule(session, allowed.telegram_id)

    # Считаем блоки по статусам
    status_counts = {"done": 0, "partial": 0, "failed": 0, "skipped": 0, "planned": 0, "active": 0}
    for b in blocks:
        if b.status in status_counts:
            status_counts[b.status] += 1

    # Считаем время по категориям
    cat_map = {c.id: c for c in categories}
    goals_map = {g.category_id: g.target_hours for g in goals}

    # Время по категориям: planned и actual
    cat_planned: dict[int, int] = {}
    cat_actual: dict[int, int] = {}

    for block in blocks:
        # Определяем категорию блока (по первой задаче)
        cat_id = None
        for tid in (block.task_ids or []):
            task = await get_task(session, tid, allowed.telegram_id)
            if task:
                cat_id = task.category_id
                break

        if cat_id is None:
            continue

        # Запланированное время
        if block.duration_type == "fixed":
            planned_min = block.duration_min or 0
        elif block.duration_type == "range":
            planned_min = (block.min_duration_min or 0 + (block.max_duration_min or 0)) // 2
        else:
            planned_min = block.max_duration_min or 60

        cat_planned[cat_id] = cat_planned.get(cat_id, 0) + planned_min

        # Фактическое время (если есть)
        if block.actual_duration_min is not None:
            cat_actual[cat_id] = cat_actual.get(cat_id, 0) + block.actual_duration_min
        elif block.status == "done" and block.duration_type == "fixed":
            cat_actual[cat_id] = cat_actual.get(cat_id, 0) + (block.duration_min or 0)

    # Формируем ответ по категориям
    cat_stats = []
    for cat in categories:
        cat_stats.append(CategoryStatsItem(
            category_id=cat.id,
            category_name=cat.name,
            category_emoji=cat.emoji,
            planned_min=cat_planned.get(cat.id, 0),
            actual_min=cat_actual.get(cat.id, 0),
            target_hours=goals_map.get(cat.id, 0),
        ))

    # Общее время
    total_planned = sum(cat_planned.values())
    total_actual = sum(cat_actual.values())

    # Свободное время — считаем из расписания
    total_available_min = 0
    for s in schedule:
        if not s.is_day_off:
            from_min = s.active_from.hour * 60 + s.active_from.minute
            to_min = s.active_to.hour * 60 + s.active_to.minute
            total_available_min += to_min - from_min

    free_time = max(0, total_available_min - total_planned)
    overload = (total_planned / total_available_min * 100) if total_available_min > 0 else 0

    # Дедлайны на этой неделе
    week_end = week_start + timedelta(days=7)
    tasks = await list_categories(session, allowed.telegram_id)  # для дедлайнов нужны задачи
    from backend.db.crud.tasks import list_tasks as lt
    all_tasks = await lt(session, allowed.telegram_id)
    upcoming_deadlines = []
    for t in all_tasks:
        if t.deadline and week_start <= t.deadline < week_end:
            upcoming_deadlines.append({
                "task_id": t.id,
                "task_name": t.name,
                "deadline": str(t.deadline),
            })

    return WeekStatsResponse(
        week_start=str(week_start),
        blocks_done=status_counts["done"],
        blocks_partial=status_counts.get("partial", 0),
        blocks_failed=status_counts["failed"],
        blocks_skipped=status_counts["skipped"],
        blocks_planned=status_counts["planned"] + status_counts["active"],
        categories=cat_stats,
        total_planned_min=total_planned,
        total_actual_min=total_actual,
        free_time_min=free_time,
        overload_percent=round(overload, 1),
        upcoming_deadlines=upcoming_deadlines,
    )


@router.get("/user/{telegram_id}")
async def get_user_stats_route(
    telegram_id: int,
    week_start: date | None = Query(None),
    admin: AllowedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Статистика пользователя (только для админа)."""
    stats = await get_user_stats(session, telegram_id, week_start)
    return stats

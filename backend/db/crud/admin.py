"""CRUD операции для админ-панели."""

import logging
from datetime import date, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AllowedUser, TaskBlock, Log

logger = logging.getLogger(__name__)


async def get_user_stats(
    session: AsyncSession,
    telegram_id: int,
    week_start: date | None = None,
) -> dict:
    """Статистика пользователя за неделю (для админа)."""
    if week_start is None:
        # Текущая неделя (понедельник)
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

    week_end = week_start + timedelta(days=7)

    # Считаем блоки по статусам
    result = await session.execute(
        select(TaskBlock.status, func.count(TaskBlock.id))
        .where(
            TaskBlock.user_id == telegram_id,
            TaskBlock.day >= week_start,
            TaskBlock.day < week_end,
        )
        .group_by(TaskBlock.status)
    )
    status_counts = dict(result.all())

    # Общее запланированное время
    result = await session.execute(
        select(func.sum(TaskBlock.duration_min))
        .where(
            TaskBlock.user_id == telegram_id,
            TaskBlock.day >= week_start,
            TaskBlock.day < week_end,
            TaskBlock.duration_type == "fixed",
        )
    )
    total_planned_min = result.scalar() or 0

    # Фактическое время (для open/range блоков)
    result = await session.execute(
        select(func.sum(TaskBlock.actual_duration_min))
        .where(
            TaskBlock.user_id == telegram_id,
            TaskBlock.day >= week_start,
            TaskBlock.day < week_end,
            TaskBlock.actual_duration_min.isnot(None),
        )
    )
    total_actual_min = result.scalar() or 0

    return {
        "telegram_id": telegram_id,
        "week_start": str(week_start),
        "blocks_by_status": {
            "planned": status_counts.get("planned", 0),
            "active": status_counts.get("active", 0),
            "done": status_counts.get("done", 0),
            "skipped": status_counts.get("skipped", 0),
            "failed": status_counts.get("failed", 0),
        },
        "total_planned_min": total_planned_min,
        "total_actual_min": total_actual_min,
    }

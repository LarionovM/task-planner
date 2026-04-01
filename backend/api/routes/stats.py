"""API маршруты для статистики (v1.4.0 — помодоро-центричная модель)."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, require_admin
from backend.api.schemas import (
    WeekStatsResponse,
    CategoryStatsItem,
    PeriodStatsResponse,
    DayStatItem,
)
from backend.db.database import get_db
from backend.db.crud.blocks import (
    list_blocks_for_week,
    get_weekly_schedule,
    get_weekly_goals,
)
from backend.db.crud.tasks import list_categories, get_task
from backend.db.crud.admin import get_user_stats
from backend.db.models import AllowedUser, TaskBlock

router = APIRouter(prefix="/api/stats", tags=["stats"])


async def _compute_cat_actual(
    session: AsyncSession,
    blocks: list[TaskBlock],
    user_id: int,
) -> dict[int, int]:
    """Считает суммарное время (мин) по категориям из помодоро-блоков."""
    cat_actual: dict[int, int] = {}
    for block in blocks:
        if block.status not in ("done", "partial"):
            continue
        if not block.task_id:
            continue
        task = await get_task(session, block.task_id, user_id)
        if not task:
            continue
        actual_min = block.actual_duration_min or block.duration_min or 25
        cat_actual[task.category_id] = cat_actual.get(task.category_id, 0) + actual_min
    return cat_actual


@router.get("/week", response_model=WeekStatsResponse)
async def get_week_stats(
    week_start: date = Query(..., description="Начало недели (понедельник)"),
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Статистика за неделю — совместимый эндпоинт."""
    blocks = await list_blocks_for_week(session, allowed.telegram_id, week_start)
    categories = await list_categories(session, allowed.telegram_id)
    goals = await get_weekly_goals(session, allowed.telegram_id)

    goals_map = {g.category_id: g.target_hours for g in goals}

    pomodoros_done = sum(1 for b in blocks if b.status == "done")
    pomodoros_partial = sum(1 for b in blocks if b.status == "partial")
    pomodoros_failed = sum(1 for b in blocks if b.status == "failed")
    pomodoros_skipped = sum(1 for b in blocks if b.status == "skipped")

    cat_actual = await _compute_cat_actual(session, blocks, allowed.telegram_id)

    from backend.db.crud.tasks import list_tasks as lt
    all_tasks = await lt(session, allowed.telegram_id)
    tasks_done = sum(1 for t in all_tasks if t.status == "done")
    tasks_in_progress = sum(1 for t in all_tasks if t.status == "in_progress")

    cat_stats = [
        CategoryStatsItem(
            category_id=cat.id,
            category_name=cat.name,
            category_emoji=cat.emoji,
            planned_min=0,
            actual_min=cat_actual.get(cat.id, 0),
            target_hours=goals_map.get(cat.id, 0),
        )
        for cat in categories
    ]

    week_end = week_start + timedelta(days=7)
    upcoming_deadlines = [
        {"task_id": t.id, "task_name": t.name, "deadline": str(t.deadline)}
        for t in all_tasks
        if t.deadline and week_start <= t.deadline < week_end
    ]

    return WeekStatsResponse(
        week_start=str(week_start),
        pomodoros_done=pomodoros_done,
        pomodoros_partial=pomodoros_partial,
        pomodoros_failed=pomodoros_failed,
        pomodoros_skipped=pomodoros_skipped,
        pomodoros_total=len(blocks),
        tasks_done=tasks_done,
        tasks_in_progress=tasks_in_progress,
        tasks_total=len(all_tasks),
        categories=cat_stats,
        total_planned_min=0,
        total_actual_min=sum(cat_actual.values()),
        free_time_min=0,
        overload_percent=0,
        upcoming_deadlines=upcoming_deadlines,
    )


@router.get("/period", response_model=PeriodStatsResponse)
async def get_period_stats(
    period: str = Query("week", description="day | week | month"),
    ref_date: date = Query(..., description="Опорная дата (любой день периода)"),
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Статистика за период: день / неделя / месяц.

    Возвращает помодоро по дням, по категориям, стрик, задачи, дедлайны.
    """
    # Определяем границы периода
    if period == "day":
        date_from = ref_date
        date_to = ref_date
    elif period == "week":
        # Начало недели (понедельник)
        dow = ref_date.weekday()
        date_from = ref_date - timedelta(days=dow)
        date_to = date_from + timedelta(days=6)
    else:  # month
        date_from = ref_date.replace(day=1)
        # Последний день месяца
        if date_from.month == 12:
            date_to = date_from.replace(year=date_from.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            date_to = date_from.replace(month=date_from.month + 1, day=1) - timedelta(days=1)

    # Получаем блоки за период
    from sqlalchemy import select
    result = await session.execute(
        select(TaskBlock).where(
            TaskBlock.user_id == allowed.telegram_id,
            TaskBlock.day >= date_from,
            TaskBlock.day <= date_to,
        ).order_by(TaskBlock.day, TaskBlock.start_time)
    )
    blocks = list(result.scalars().all())

    # Статистика по статусам
    pomodoros_done = sum(1 for b in blocks if b.status == "done")
    pomodoros_partial = sum(1 for b in blocks if b.status == "partial")
    pomodoros_failed = sum(1 for b in blocks if b.status == "failed")
    pomodoros_skipped = sum(1 for b in blocks if b.status == "skipped")
    focus_min = sum(
        (b.actual_duration_min or b.duration_min or 25)
        for b in blocks if b.status in ("done", "partial")
    )

    # По дням
    days_range = (date_to - date_from).days + 1
    day_stats: dict[str, DayStatItem] = {}
    for i in range(days_range):
        d = date_from + timedelta(days=i)
        day_stats[str(d)] = DayStatItem(date=str(d))

    for block in blocks:
        ds = str(block.day)
        if ds not in day_stats:
            continue
        day_stats[ds].pomodoros_total += 1
        if block.status == "done":
            day_stats[ds].pomodoros_done += 1
            day_stats[ds].focus_min += block.actual_duration_min or block.duration_min or 25

    # Стрик — идём от сегодня назад
    today = date.today()
    streak = 0
    check_date = today
    while True:
        ds = str(check_date)
        if ds in day_stats and day_stats[ds].pomodoros_done > 0:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            # Проверим дни до начала периода — нужно запросить ещё
            if check_date < date_from:
                # Ищем в более старых данных
                r2 = await session.execute(
                    select(TaskBlock).where(
                        TaskBlock.user_id == allowed.telegram_id,
                        TaskBlock.day == check_date,
                        TaskBlock.status == "done",
                    )
                )
                if r2.scalars().first():
                    streak += 1
                    check_date -= timedelta(days=1)
                    continue
            break

    # Среднее помодоро в день (только в дни где было хоть одно)
    active_days = sum(1 for ds in day_stats.values() if ds.pomodoros_total > 0)
    avg_per_day = round(pomodoros_done / active_days, 1) if active_days > 0 else 0.0

    # По категориям
    categories = await list_categories(session, allowed.telegram_id)
    goals = await get_weekly_goals(session, allowed.telegram_id)
    goals_map = {g.category_id: g.target_hours for g in goals}
    cat_actual = await _compute_cat_actual(session, blocks, allowed.telegram_id)

    cat_stats = [
        CategoryStatsItem(
            category_id=cat.id,
            category_name=cat.name,
            category_emoji=cat.emoji,
            planned_min=0,
            actual_min=cat_actual.get(cat.id, 0),
            target_hours=goals_map.get(cat.id, 0),
        )
        for cat in categories
        if cat_actual.get(cat.id, 0) > 0
    ]

    # Задачи
    from backend.db.crud.tasks import list_tasks as lt
    all_tasks = await lt(session, allowed.telegram_id)
    tasks_done = sum(1 for t in all_tasks if t.status == "done")
    tasks_in_progress = sum(1 for t in all_tasks if t.status == "in_progress")

    # Дедлайны в периоде
    upcoming_deadlines = [
        {"task_id": t.id, "task_name": t.name, "deadline": str(t.deadline)}
        for t in all_tasks
        if t.deadline and date_from <= t.deadline <= date_to and t.status != "done"
    ]

    return PeriodStatsResponse(
        period=period,
        date_from=str(date_from),
        date_to=str(date_to),
        pomodoros_done=pomodoros_done,
        pomodoros_partial=pomodoros_partial,
        pomodoros_failed=pomodoros_failed,
        pomodoros_skipped=pomodoros_skipped,
        pomodoros_total=len(blocks),
        focus_min=focus_min,
        streak_days=streak,
        avg_per_day=avg_per_day,
        by_day=list(day_stats.values()),
        categories=cat_stats,
        tasks_done=tasks_done,
        tasks_in_progress=tasks_in_progress,
        tasks_total=len(all_tasks),
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

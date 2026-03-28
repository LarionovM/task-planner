"""CRUD операции для блоков, расписания, целей и логов."""

import logging
from datetime import date, time, datetime, timedelta
from typing import Any

from sqlalchemy import select, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    TaskBlock,
    WeeklySchedule,
    WeeklyGoal,
    Log,
    Task,
)

logger = logging.getLogger(__name__)


# === Блоки ===


def _time_to_minutes(t: time) -> int:
    """Переводит time в минуты от начала дня."""
    return t.hour * 60 + t.minute


def _check_blocks_overlap(
    existing_blocks: list[TaskBlock],
    new_start: time,
    new_duration: int,
    exclude_block_id: int | None = None,
) -> list[dict]:
    """Проверяет пересечение нового блока с существующими."""
    warnings = []
    new_start_min = _time_to_minutes(new_start)
    new_end_min = new_start_min + new_duration

    for block in existing_blocks:
        if exclude_block_id and block.id == exclude_block_id:
            continue

        block_start_min = _time_to_minutes(block.start_time)
        # Определяем длительность блока в зависимости от типа
        if block.duration_type == "fixed":
            block_dur = block.duration_min or 0
        elif block.duration_type == "range":
            block_dur = block.max_duration_min or block.min_duration_min or 60
        else:  # open
            block_dur = block.max_duration_min or 60
        block_end_min = block_start_min + block_dur

        # Проверяем пересечение
        if new_start_min < block_end_min and new_end_min > block_start_min:
            block_name = block.block_name or f"Блок #{block.id}"
            start_str = block.start_time.strftime("%H:%M")
            end_h, end_m = divmod(block_end_min, 60)
            warnings.append({
                "type": "overlap",
                "block_id": block.id,
                "message": f"Пересечение с блоком «{block_name}» ({start_str}–{end_h:02d}:{end_m:02d})",
            })

    return warnings


async def list_blocks_for_week(
    session: AsyncSession,
    user_id: int,
    week_start: date,
) -> list[TaskBlock]:
    """Блоки на неделю (7 дней начиная с week_start)."""
    week_end = week_start + timedelta(days=7)
    result = await session.execute(
        select(TaskBlock)
        .where(
            TaskBlock.user_id == user_id,
            TaskBlock.day >= week_start,
            TaskBlock.day < week_end,
        )
        .order_by(TaskBlock.day, TaskBlock.start_time)
    )
    return list(result.scalars().all())


async def get_block(
    session: AsyncSession, block_id: int, user_id: int
) -> TaskBlock | None:
    """Получить блок по ID."""
    result = await session.execute(
        select(TaskBlock).where(
            TaskBlock.id == block_id,
            TaskBlock.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def create_block(
    session: AsyncSession, user_id: int, **kwargs
) -> dict[str, Any]:
    """Создать блок. Возвращает блок + предупреждения о пересечениях."""
    day = kwargs.get("day")
    start_time = kwargs.get("start_time")
    duration_type = kwargs.get("duration_type", "fixed")

    # Определяем длительность для проверки пересечений
    if duration_type == "fixed":
        check_duration = kwargs.get("duration_min", 60)
    elif duration_type == "range":
        check_duration = kwargs.get("max_duration_min", 60)
    else:
        check_duration = kwargs.get("max_duration_min") or 60

    # Получаем существующие блоки на этот день
    existing = await session.execute(
        select(TaskBlock).where(
            TaskBlock.user_id == user_id,
            TaskBlock.day == day,
        )
    )
    existing_blocks = list(existing.scalars().all())

    # Проверяем пересечения
    warnings = _check_blocks_overlap(existing_blocks, start_time, check_duration)

    # Проверяем зависимости задач
    task_ids = kwargs.get("task_ids", [])
    dep_warnings = await _check_dependency_order(
        session, user_id, task_ids, day, start_time, existing_blocks
    )
    warnings.extend(dep_warnings)

    # Определяем is_mixed по уникальным task_ids
    unique_ids = set(task_ids)
    kwargs["is_mixed"] = len(unique_ids) > 1

    # Определяем block_name если не задано — с поддержкой дубликатов (xN)
    if not kwargs.get("block_name") and task_ids:
        from collections import Counter
        task_counts = Counter(task_ids)
        tasks_result = await session.execute(
            select(Task).where(Task.id.in_(list(unique_ids)))
        )
        task_map = {t.id: t for t in tasks_result.scalars().all()}
        name_parts = []
        for tid, count in task_counts.items():
            t = task_map.get(tid)
            if t:
                name_parts.append(f"{t.name} x{count}" if count > 1 else t.name)
        if name_parts:
            kwargs.setdefault("block_name", ", ".join(name_parts))

    block = TaskBlock(user_id=user_id, **kwargs)
    session.add(block)
    await session.flush()

    return {"block": block, "warnings": warnings}


async def _check_dependency_order(
    session: AsyncSession,
    user_id: int,
    task_ids: list[int],
    day: date,
    start_time: time,
    existing_blocks: list[TaskBlock],
) -> list[dict]:
    """Проверяет не нарушен ли порядок зависимостей."""
    warnings = []
    if not task_ids:
        return warnings

    # Получаем задачи с зависимостями
    tasks_result = await session.execute(
        select(Task).where(Task.id.in_(task_ids), Task.user_id == user_id)
    )
    tasks = list(tasks_result.scalars().all())

    for task in tasks:
        if not task.depends_on:
            continue
        # Проверяем что зависимые задачи запланированы раньше
        for dep_id in task.depends_on:
            for block in existing_blocks:
                if dep_id in (block.task_ids or []):
                    if block.day > day or (
                        block.day == day and block.start_time >= start_time
                    ):
                        warnings.append({
                            "type": "dependency",
                            "message": f"Задача «{task.name}» зависит от задачи #{dep_id}, которая запланирована позже",
                        })

    return warnings


async def update_block(
    session: AsyncSession, block_id: int, user_id: int, **kwargs
) -> dict[str, Any] | None:
    """Обновить блок. Возвращает блок + is_active флаг."""
    block = await get_block(session, block_id, user_id)
    if block is None:
        return None

    is_active = block.status == "active"

    # Если меняется день или время у проваленного/пропущенного блока — сбросить статус на planned
    changing_schedule = "day" in kwargs or "start_time" in kwargs
    if changing_schedule and block.status in ("failed", "skipped"):
        block.status = "planned"
        # Сбросить фактическое время (оно больше не актуально)
        block.actual_start_at = None
        block.actual_end_at = None
        block.actual_duration_min = None

    for key, value in kwargs.items():
        if hasattr(block, key):
            setattr(block, key, value)

    await session.flush()
    return {"block": block, "is_active": is_active}


async def delete_block(
    session: AsyncSession, block_id: int, user_id: int
) -> bool:
    """Удалить блок."""
    block = await get_block(session, block_id, user_id)
    if block is None:
        return False
    await session.delete(block)
    await session.flush()
    return True


async def get_affected_blocks(
    session: AsyncSession, task_id: int, user_id: int
) -> list[TaskBlock]:
    """Блоки, содержащие указанную задачу."""
    result = await session.execute(
        select(TaskBlock).where(
            TaskBlock.user_id == user_id,
            TaskBlock.status.in_(["planned", "active"]),
        )
    )
    all_blocks = list(result.scalars().all())
    return [b for b in all_blocks if task_id in (b.task_ids or [])]


# === Расписание недели ===


async def get_weekly_schedule(
    session: AsyncSession, user_id: int
) -> list[WeeklySchedule]:
    """Расписание на неделю."""
    result = await session.execute(
        select(WeeklySchedule)
        .where(WeeklySchedule.user_id == user_id)
        .order_by(WeeklySchedule.day_of_week)
    )
    return list(result.scalars().all())


async def upsert_weekly_schedule(
    session: AsyncSession,
    user_id: int,
    days: list[dict],
) -> list[WeeklySchedule]:
    """Обновить расписание всех 7 дней."""
    # Удаляем старое
    await session.execute(
        delete(WeeklySchedule).where(WeeklySchedule.user_id == user_id)
    )

    schedules = []
    for day_data in days:
        schedule = WeeklySchedule(
            user_id=user_id,
            day_of_week=day_data["day_of_week"],
            is_day_off=day_data.get("is_day_off", False),
            active_from=day_data.get("active_from", time(9, 0)),
            active_to=day_data.get("active_to", time(18, 0)),
        )
        session.add(schedule)
        schedules.append(schedule)

    await session.flush()
    return schedules


# === Цели по категориям ===


async def get_weekly_goals(
    session: AsyncSession, user_id: int
) -> list[WeeklyGoal]:
    """Цели на неделю по категориям."""
    result = await session.execute(
        select(WeeklyGoal).where(WeeklyGoal.user_id == user_id)
    )
    return list(result.scalars().all())


async def upsert_weekly_goals(
    session: AsyncSession,
    user_id: int,
    goals: list[dict],
) -> list[WeeklyGoal]:
    """Обновить цели на неделю."""
    # Удаляем старые
    await session.execute(
        delete(WeeklyGoal).where(WeeklyGoal.user_id == user_id)
    )

    result = []
    for goal_data in goals:
        goal = WeeklyGoal(
            user_id=user_id,
            category_id=goal_data["category_id"],
            target_hours=goal_data.get("target_hours", 0),
        )
        session.add(goal)
        result.append(goal)

    await session.flush()
    return result


# === Логи ===


async def create_log(
    session: AsyncSession,
    user_id: int,
    event_type: str,
    task_block_id: int | None = None,
    payload: dict | None = None,
) -> Log:
    """Создать лог-запись."""
    log = Log(
        user_id=user_id,
        task_block_id=task_block_id,
        event_type=event_type,
        payload=payload or {},
    )
    session.add(log)
    await session.flush()
    return log


async def get_day_logs(
    session: AsyncSession,
    user_id: int,
    day: date,
) -> list[Log]:
    """Логи за день."""
    start = datetime.combine(day, time(0, 0))
    end = datetime.combine(day + timedelta(days=1), time(0, 0))
    result = await session.execute(
        select(Log)
        .where(
            Log.user_id == user_id,
            Log.created_at >= start,
            Log.created_at < end,
        )
        .order_by(Log.created_at)
    )
    return list(result.scalars().all())


async def get_blocks_for_day(
    session: AsyncSession,
    user_id: int,
    day: date,
) -> list[TaskBlock]:
    """Все блоки на конкретный день."""
    result = await session.execute(
        select(TaskBlock)
        .where(
            TaskBlock.user_id == user_id,
            TaskBlock.day == day,
        )
        .order_by(TaskBlock.start_time)
    )
    return list(result.scalars().all())


async def get_planned_blocks_from_today(
    session: AsyncSession,
    today: date | None = None,
) -> list[TaskBlock]:
    """Все planned блоки начиная с сегодня (для восстановления scheduler)."""
    if today is None:
        today = date.today()
    result = await session.execute(
        select(TaskBlock).where(
            TaskBlock.status == "planned",
            TaskBlock.day >= today,
        )
    )
    return list(result.scalars().all())


async def get_active_blocks(
    session: AsyncSession,
) -> list[TaskBlock]:
    """Все активные блоки (для восстановления при рестарте)."""
    result = await session.execute(
        select(TaskBlock).where(
            TaskBlock.status == "active",
            TaskBlock.actual_end_at.is_(None),
        )
    )
    return list(result.scalars().all())


async def check_empty_slots_and_backlog(
    session: AsyncSession,
    user_id: int,
    target_date: date,
) -> dict[str, Any]:
    """Проверяет наличие свободных слотов и нераспределённых задач.

    Возвращает:
    - has_free_slots: bool — есть ли свободные 30-мин слоты в рабочее время
    - has_unassigned_tasks: bool — есть ли задачи в бэклоге без блоков на этот день
    - free_minutes: int — количество свободных минут
    - unassigned_count: int — количество нераспределённых задач
    - should_remind: bool — оба условия выполнены
    """
    # 1. Получаем расписание на день недели
    weekday = target_date.weekday()  # 0=Пн
    schedule = await get_weekly_schedule(session, user_id)
    day_schedule = next((s for s in schedule if s.day_of_week == weekday), None)

    if not day_schedule or day_schedule.is_day_off:
        return {"has_free_slots": False, "has_unassigned_tasks": False,
                "free_minutes": 0, "unassigned_count": 0, "should_remind": False}

    # 2. Рабочее время в минутах
    work_start = _time_to_minutes(day_schedule.active_from)
    work_end = _time_to_minutes(day_schedule.active_to)
    total_work_min = work_end - work_start

    # 3. Блоки на этот день
    blocks = await get_blocks_for_day(session, user_id, target_date)
    occupied_min = 0
    for block in blocks:
        if block.duration_type == "fixed":
            occupied_min += block.duration_min or 0
        elif block.duration_type == "range":
            occupied_min += block.max_duration_min or block.min_duration_min or 30
        else:  # open
            occupied_min += block.max_duration_min or 60

    free_minutes = max(0, total_work_min - occupied_min)
    has_free_slots = free_minutes >= 30  # хотя бы один 30-мин слот

    # 4. Нераспределённые задачи: не recurring, не is_epic, не удалённые
    # Или recurring с recur_days включающим этот день
    all_tasks = await session.execute(
        select(Task).where(
            Task.user_id == user_id,
            Task.is_deleted == False,
            Task.is_epic == False,
        )
    )
    tasks = list(all_tasks.scalars().all())

    # ID задач, уже распределённых в блоки на этот день
    assigned_task_ids = set()
    for block in blocks:
        assigned_task_ids.update(block.task_ids or [])

    # Считаем нераспределённые
    unassigned = []
    for task in tasks:
        if task.id in assigned_task_ids:
            continue
        # Recurring задачи — только если этот день в recur_days
        if task.is_recurring:
            if weekday not in (task.recur_days or []):
                continue
        unassigned.append(task)

    unassigned_count = len(unassigned)
    has_unassigned = unassigned_count > 0

    return {
        "has_free_slots": has_free_slots,
        "has_unassigned_tasks": has_unassigned,
        "free_minutes": free_minutes,
        "unassigned_count": unassigned_count,
        "should_remind": has_free_slots and has_unassigned,
    }

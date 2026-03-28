"""CRUD операции для категорий и задач."""

import logging
from typing import Any

from sqlalchemy import select, update, delete, func, case, literal
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Category, Task, TaskBlock

logger = logging.getLogger(__name__)


# === Категории ===


async def list_categories(
    session: AsyncSession, user_id: int
) -> list[Category]:
    """Список категорий пользователя, отсортированных по sort_order."""
    result = await session.execute(
        select(Category)
        .where(Category.user_id == user_id)
        .order_by(Category.sort_order)
    )
    return list(result.scalars().all())


async def create_category(
    session: AsyncSession,
    user_id: int,
    name: str,
    emoji: str | None = None,
    color: str | None = None,
) -> Category:
    """Создать категорию."""
    # Определяем sort_order — следующий по порядку
    result = await session.execute(
        select(func.max(Category.sort_order))
        .where(Category.user_id == user_id)
    )
    max_order = result.scalar() or 0

    cat = Category(
        name=name,
        emoji=emoji,
        color=color,
        user_id=user_id,
        sort_order=max_order + 1,
    )
    session.add(cat)
    await session.flush()
    return cat


async def update_category(
    session: AsyncSession,
    category_id: int,
    user_id: int,
    **kwargs,
) -> Category | None:
    """Обновить категорию."""
    result = await session.execute(
        select(Category).where(
            Category.id == category_id,
            Category.user_id == user_id,
        )
    )
    cat = result.scalar_one_or_none()
    if cat is None:
        return None

    for key, value in kwargs.items():
        if hasattr(cat, key) and value is not None:
            setattr(cat, key, value)

    await session.flush()
    return cat


async def delete_category(
    session: AsyncSession,
    category_id: int,
    user_id: int,
) -> dict[str, Any]:
    """Удалить категорию. Возвращает информацию о связанных задачах."""
    # Проверяем есть ли задачи в этой категории
    task_count_result = await session.execute(
        select(func.count(Task.id)).where(
            Task.category_id == category_id,
            Task.user_id == user_id,
            Task.is_deleted == False,
        )
    )
    task_count = task_count_result.scalar() or 0

    if task_count > 0:
        return {
            "deleted": False,
            "has_tasks": True,
            "task_count": task_count,
            "message": f"Категория содержит {task_count} задач. Удалите или переназначьте их.",
        }

    result = await session.execute(
        select(Category).where(
            Category.id == category_id,
            Category.user_id == user_id,
        )
    )
    cat = result.scalar_one_or_none()
    if cat is None:
        return {"deleted": False, "has_tasks": False, "message": "Категория не найдена"}

    await session.delete(cat)
    await session.flush()
    return {"deleted": True, "has_tasks": False}


async def reorder_categories(
    session: AsyncSession,
    user_id: int,
    category_ids: list[int],
) -> None:
    """Изменить порядок категорий."""
    for i, cat_id in enumerate(category_ids):
        await session.execute(
            update(Category)
            .where(Category.id == cat_id, Category.user_id == user_id)
            .values(sort_order=i)
        )
    await session.flush()


async def reassign_tasks_category(
    session: AsyncSession,
    user_id: int,
    from_category_id: int,
    to_category_id: int,
) -> int:
    """Переназначить задачи из одной категории в другую."""
    result = await session.execute(
        update(Task)
        .where(
            Task.category_id == from_category_id,
            Task.user_id == user_id,
            Task.is_deleted == False,
        )
        .values(category_id=to_category_id)
    )
    await session.flush()
    return result.rowcount


# === Задачи ===


async def list_tasks(
    session: AsyncSession,
    user_id: int,
    category_id: int | None = None,
    priority: str | None = None,
    tag: str | None = None,
    has_deadline: bool | None = None,
    sort_by: str = "created_at",
) -> list[Task]:
    """Список задач с фильтрами."""
    query = select(Task).where(
        Task.user_id == user_id,
        Task.is_deleted == False,
    )

    if category_id is not None:
        query = query.where(Task.category_id == category_id)

    if priority is not None:
        query = query.where(Task.priority == priority)

    if has_deadline is True:
        query = query.where(Task.deadline.isnot(None))
    elif has_deadline is False:
        query = query.where(Task.deadline.is_(None))

    # Сортировка
    if sort_by == "priority":
        # high > medium > low
        priority_order = case(
            (Task.priority == "high", literal(0)),
            (Task.priority == "medium", literal(1)),
            (Task.priority == "low", literal(2)),
            else_=literal(3),
        )
        query = query.order_by(priority_order)
    elif sort_by == "deadline":
        query = query.order_by(Task.deadline.asc().nulls_last())
    elif sort_by == "name":
        query = query.order_by(Task.name)
    else:
        query = query.order_by(Task.created_at.desc())

    result = await session.execute(query)
    tasks = list(result.scalars().all())

    # Фильтрация по тегу (JSON array, нужна post-фильтрация)
    if tag is not None:
        tasks = [t for t in tasks if tag in (t.tags or [])]

    return tasks


async def get_task(
    session: AsyncSession, task_id: int, user_id: int
) -> Task | None:
    """Получить задачу по ID."""
    result = await session.execute(
        select(Task).where(
            Task.id == task_id,
            Task.user_id == user_id,
            Task.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


async def create_task(
    session: AsyncSession, user_id: int, **kwargs
) -> Task:
    """Создать задачу."""
    task = Task(user_id=user_id, **kwargs)
    session.add(task)
    await session.flush()
    return task


async def update_task(
    session: AsyncSession, task_id: int, user_id: int, **kwargs
) -> Task | None:
    """Обновить задачу."""
    task = await get_task(session, task_id, user_id)
    if task is None:
        return None

    for key, value in kwargs.items():
        if hasattr(task, key):
            setattr(task, key, value)

    await session.flush()
    return task


async def soft_delete_task(
    session: AsyncSession, task_id: int, user_id: int
) -> dict[str, Any]:
    """Soft delete задачи. Возвращает список затронутых блоков."""
    task = await get_task(session, task_id, user_id)
    if task is None:
        return {"deleted": False, "affected_blocks": []}

    # Ищем блоки где эта задача используется
    result = await session.execute(
        select(TaskBlock).where(
            TaskBlock.user_id == user_id,
            TaskBlock.status.in_(["planned", "active"]),
        )
    )
    all_blocks = list(result.scalars().all())
    affected = [b for b in all_blocks if task_id in (b.task_ids or [])]

    task.is_deleted = True
    await session.flush()

    return {
        "deleted": True,
        "affected_blocks": [
            {"id": b.id, "block_name": b.block_name, "day": str(b.day)}
            for b in affected
        ],
    }

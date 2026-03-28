"""API маршруты для задач."""

from datetime import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.api.schemas import (
    TaskCreate,
    TaskUpdate,
    TaskResponse,
    TaskDeleteResponse,
)
from backend.db.database import get_db
from backend.db.crud.tasks import (
    list_tasks,
    get_task,
    create_task,
    update_task,
    soft_delete_task,
)
from backend.db.models import AllowedUser

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskResponse])
async def get_tasks(
    category_id: int | None = Query(None),
    priority: str | None = Query(None),
    tag: str | None = Query(None),
    has_deadline: bool | None = Query(None),
    sort_by: str = Query("created_at"),
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Список задач с фильтрами."""
    tasks = await list_tasks(
        session,
        user_id=allowed.telegram_id,
        category_id=category_id,
        priority=priority,
        tag=tag,
        has_deadline=has_deadline,
        sort_by=sort_by,
    )
    return [TaskResponse.model_validate(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_by_id(
    task_id: int,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Получить задачу по ID."""
    task = await get_task(session, task_id, allowed.telegram_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return TaskResponse.model_validate(task)


@router.post("", response_model=TaskResponse, status_code=201)
async def post_task(
    data: TaskCreate,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Создать задачу."""
    dump = data.model_dump()
    # Конвертация preferred_time из строки в time
    if dump.get("preferred_time"):
        parts = dump["preferred_time"].split(":")
        dump["preferred_time"] = time(int(parts[0]), int(parts[1]))
    task = await create_task(
        session,
        user_id=allowed.telegram_id,
        **dump,
    )
    return TaskResponse.model_validate(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def patch_task(
    task_id: int,
    data: TaskUpdate,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Обновить задачу."""
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    # Конвертация preferred_time из строки в time
    if "preferred_time" in kwargs and kwargs["preferred_time"]:
        parts = kwargs["preferred_time"].split(":")
        kwargs["preferred_time"] = time(int(parts[0]), int(parts[1]))
    task = await update_task(session, task_id, allowed.telegram_id, **kwargs)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}", response_model=TaskDeleteResponse)
async def delete_task_route(
    task_id: int,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Soft delete задачи. Возвращает затронутые блоки."""
    result = await soft_delete_task(session, task_id, allowed.telegram_id)
    if not result["deleted"]:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return TaskDeleteResponse(**result)

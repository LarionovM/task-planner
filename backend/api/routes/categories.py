"""API маршруты для категорий."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.api.schemas import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    CategoryReorder,
    CategoryReassign,
    CategoryDeleteResponse,
)
from backend.db.database import get_db
from backend.db.crud.tasks import (
    list_categories,
    create_category,
    update_category,
    delete_category,
    reorder_categories,
    reassign_tasks_category,
)
from backend.db.models import AllowedUser

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
async def get_categories(
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Список категорий пользователя."""
    cats = await list_categories(session, allowed.telegram_id)
    return [CategoryResponse.model_validate(c) for c in cats]


@router.post("", response_model=CategoryResponse, status_code=201)
async def post_category(
    data: CategoryCreate,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Создать категорию."""
    cat = await create_category(
        session,
        user_id=allowed.telegram_id,
        name=data.name,
        emoji=data.emoji,
        color=data.color,
    )
    return CategoryResponse.model_validate(cat)


@router.patch("/{category_id}", response_model=CategoryResponse)
async def patch_category(
    category_id: int,
    data: CategoryUpdate,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Обновить категорию."""
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    cat = await update_category(
        session, category_id, allowed.telegram_id, **kwargs
    )
    if cat is None:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    return CategoryResponse.model_validate(cat)


@router.delete("/{category_id}", response_model=CategoryDeleteResponse)
async def delete_category_route(
    category_id: int,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Удалить категорию. Вернёт ошибку если есть задачи."""
    result = await delete_category(session, category_id, allowed.telegram_id)
    return CategoryDeleteResponse(**result)


@router.post("/{category_id}/reassign")
async def reassign_category_tasks(
    category_id: int,
    data: CategoryReassign,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Переназначить задачи из одной категории в другую, затем удалить."""
    count = await reassign_tasks_category(
        session, allowed.telegram_id, category_id, data.to_category_id
    )
    # Теперь удаляем категорию (задач уже нет)
    result = await delete_category(session, category_id, allowed.telegram_id)
    return {"reassigned_tasks": count, **result}


@router.post("/reorder")
async def reorder_categories_route(
    data: CategoryReorder,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Изменить порядок категорий."""
    await reorder_categories(session, allowed.telegram_id, data.category_ids)
    return {"ok": True}

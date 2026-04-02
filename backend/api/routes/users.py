"""API маршруты для пользователей и настроек (v1.2.0)."""

from datetime import time

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.api.schemas import (
    UserResponse,
    UserSettingsUpdate,
    SpamConfigResponse,
    SpamConfigUpdate,
)
from backend.db.database import get_db
from backend.db.crud.users import (
    get_or_create_user,
    update_user_settings,
    get_spam_config,
    update_spam_config,
)
from backend.db.models import AllowedUser

router = APIRouter(prefix="/api/users", tags=["users"])


def _time_to_str(t: time | None) -> str:
    """Конвертирует time в строку HH:MM."""
    if t is None:
        return "00:00"
    return t.strftime("%H:%M")


def _str_to_time(s: str) -> time:
    """Конвертирует строку HH:MM в time."""
    parts = s.split(":")
    return time(int(parts[0]), int(parts[1]))


@router.get("/me", response_model=UserResponse)
async def get_me(
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Получить данные текущего пользователя."""
    user = await get_or_create_user(session, allowed.telegram_id)
    return UserResponse(
        telegram_id=user.telegram_id,
        timezone=user.timezone,
        day_start_time=_time_to_str(user.day_start_time) if user.day_start_time else "08:00",
        day_end_time=_time_to_str(user.day_end_time),
        pomodoro_work_min=user.pomodoro_work_min if hasattr(user, 'pomodoro_work_min') and user.pomodoro_work_min else 25,
        pomodoro_short_break_min=user.pomodoro_short_break_min if hasattr(user, 'pomodoro_short_break_min') and user.pomodoro_short_break_min else 5,
        pomodoro_long_break_min=user.pomodoro_long_break_min if hasattr(user, 'pomodoro_long_break_min') and user.pomodoro_long_break_min else 30,
        pomodoro_cycles_before_long=user.pomodoro_cycles_before_long if hasattr(user, 'pomodoro_cycles_before_long') and user.pomodoro_cycles_before_long else 4,
        reminders_paused_until=user.reminders_paused_until if hasattr(user, 'reminders_paused_until') else None,
        reminders_stopped=user.reminders_stopped if hasattr(user, 'reminders_stopped') else False,
        productive_mode_enabled=user.productive_mode_enabled if hasattr(user, 'productive_mode_enabled') else False,
        is_admin=allowed.is_admin,
        is_active=allowed.is_active,
        created_at=user.created_at,
    )


@router.patch("/me/settings", response_model=UserResponse)
async def patch_settings(
    data: UserSettingsUpdate,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Обновить настройки пользователя."""
    kwargs = {}
    if data.timezone is not None:
        kwargs["timezone"] = data.timezone
    if data.day_start_time is not None:
        kwargs["day_start_time"] = _str_to_time(data.day_start_time)
    if data.day_end_time is not None:
        kwargs["day_end_time"] = _str_to_time(data.day_end_time)
    if data.pomodoro_work_min is not None:
        kwargs["pomodoro_work_min"] = data.pomodoro_work_min
    if data.pomodoro_short_break_min is not None:
        kwargs["pomodoro_short_break_min"] = data.pomodoro_short_break_min
    if data.pomodoro_long_break_min is not None:
        kwargs["pomodoro_long_break_min"] = data.pomodoro_long_break_min
    if data.pomodoro_cycles_before_long is not None:
        kwargs["pomodoro_cycles_before_long"] = data.pomodoro_cycles_before_long
    if data.productive_mode_enabled is not None:
        kwargs["productive_mode_enabled"] = data.productive_mode_enabled

    user = await update_user_settings(session, allowed.telegram_id, **kwargs)
    return UserResponse(
        telegram_id=user.telegram_id,
        timezone=user.timezone,
        day_start_time=_time_to_str(user.day_start_time) if user.day_start_time else "08:00",
        day_end_time=_time_to_str(user.day_end_time),
        pomodoro_work_min=user.pomodoro_work_min if hasattr(user, 'pomodoro_work_min') and user.pomodoro_work_min else 25,
        pomodoro_short_break_min=user.pomodoro_short_break_min if hasattr(user, 'pomodoro_short_break_min') and user.pomodoro_short_break_min else 5,
        pomodoro_long_break_min=user.pomodoro_long_break_min if hasattr(user, 'pomodoro_long_break_min') and user.pomodoro_long_break_min else 30,
        pomodoro_cycles_before_long=user.pomodoro_cycles_before_long if hasattr(user, 'pomodoro_cycles_before_long') and user.pomodoro_cycles_before_long else 4,
        reminders_paused_until=user.reminders_paused_until if hasattr(user, 'reminders_paused_until') else None,
        reminders_stopped=user.reminders_stopped if hasattr(user, 'reminders_stopped') else False,
        productive_mode_enabled=user.productive_mode_enabled if hasattr(user, 'productive_mode_enabled') else False,
        is_admin=allowed.is_admin,
        is_active=allowed.is_active,
        created_at=user.created_at,
    )


@router.get("/me/spam-config", response_model=SpamConfigResponse)
async def get_my_spam_config(
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Получить настройки спама."""
    config = await get_spam_config(session, allowed.telegram_id)
    return SpamConfigResponse(
        initial_interval_sec=config.initial_interval_sec,
        multiplier=config.multiplier,
        max_interval_sec=config.max_interval_sec,
        enabled=config.enabled,
        spam_category_ids=config.spam_category_ids or [],
    )


@router.patch("/me/spam-config", response_model=SpamConfigResponse)
async def patch_spam_config(
    data: SpamConfigUpdate,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Обновить настройки спама."""
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    config = await update_spam_config(session, allowed.telegram_id, **kwargs)
    return SpamConfigResponse(
        initial_interval_sec=config.initial_interval_sec,
        multiplier=config.multiplier,
        max_interval_sec=config.max_interval_sec,
        enabled=config.enabled,
        spam_category_ids=config.spam_category_ids or [],
    )

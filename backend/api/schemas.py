"""Pydantic v2 схемы для API (v1.2.0)."""

from datetime import date, time, datetime
from pydantic import BaseModel, Field, field_serializer, field_validator


# === Пользователи ===


class UserResponse(BaseModel):
    telegram_id: int
    timezone: str
    day_start_time: str
    day_end_time: str
    pomodoro_work_min: int = 25
    pomodoro_short_break_min: int = 5
    pomodoro_long_break_min: int = 30
    pomodoro_cycles_before_long: int = 4
    reminders_paused_until: datetime | None = None
    reminders_stopped: bool = False
    is_admin: bool = False
    is_active: bool = True
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserSettingsUpdate(BaseModel):
    timezone: str | None = None
    day_start_time: str | None = None  # HH:MM
    day_end_time: str | None = None
    pomodoro_work_min: int | None = None
    pomodoro_short_break_min: int | None = None
    pomodoro_long_break_min: int | None = None
    pomodoro_cycles_before_long: int | None = None


class SpamConfigResponse(BaseModel):
    initial_interval_sec: int
    multiplier: float
    max_interval_sec: int
    enabled: bool
    spam_category_ids: list[int]

    model_config = {"from_attributes": True}


class SpamConfigUpdate(BaseModel):
    initial_interval_sec: int | None = None
    multiplier: float | None = None
    max_interval_sec: int | None = None
    enabled: bool | None = None
    spam_category_ids: list[int] | None = None


# === Категории ===


class CategoryCreate(BaseModel):
    name: str
    emoji: str | None = None
    color: str | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    emoji: str | None = None
    color: str | None = None


class CategoryResponse(BaseModel):
    id: int
    name: str
    emoji: str | None
    color: str | None
    sort_order: int

    model_config = {"from_attributes": True}


class CategoryReorder(BaseModel):
    category_ids: list[int]


class CategoryReassign(BaseModel):
    to_category_id: int


class CategoryDeleteResponse(BaseModel):
    deleted: bool
    has_tasks: bool = False
    task_count: int = 0
    message: str = ""


# === Задачи (v1.2.0 — упрощённые) ===


class TaskCreate(BaseModel):
    name: str
    category_id: int
    estimated_time_min: int | None = None
    priority: str = "medium"
    status: str = "grooming"  # grooming / in_progress / blocked / done
    description: str | None = None
    link: str | None = None
    is_recurring: bool = False
    recur_days: list[int] = Field(default_factory=list)
    scheduled_date: date | None = None
    deadline: date | None = None
    tags: list[str] = Field(default_factory=list)
    depends_on: list[int] = Field(default_factory=list)
    spam_enabled: bool = True
    is_epic: bool = False
    epic_id: int | None = None
    epic_emoji: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = ("grooming", "in_progress", "blocked", "done")
        if v not in allowed:
            raise ValueError(f"status must be one of: {', '.join(allowed)}")
        return v


class TaskUpdate(BaseModel):
    name: str | None = None
    category_id: int | None = None
    estimated_time_min: int | None = None
    priority: str | None = None
    status: str | None = None
    description: str | None = None
    link: str | None = None
    is_recurring: bool | None = None
    recur_days: list[int] | None = None
    scheduled_date: date | None = None
    deadline: date | None = None
    tags: list[str] | None = None
    depends_on: list[int] | None = None
    spam_enabled: bool | None = None
    is_epic: bool | None = None
    epic_id: int | None = None
    epic_emoji: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None:
            allowed = ("grooming", "in_progress", "blocked", "done")
            if v not in allowed:
                raise ValueError(f"status must be one of: {', '.join(allowed)}")
        return v


class TaskResponse(BaseModel):
    id: int
    name: str
    category_id: int
    estimated_time_min: int | None
    priority: str
    status: str
    description: str | None = None
    link: str | None = None
    is_recurring: bool
    recur_days: list[int]
    scheduled_date: date | None = None
    deadline: date | None
    tags: list[str]
    depends_on: list[int]
    spam_enabled: bool
    is_epic: bool = False
    epic_id: int | None = None
    epic_emoji: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskDeleteResponse(BaseModel):
    deleted: bool
    affected_blocks: list[dict] = Field(default_factory=list)


# === События (v1.2.0 — созвоны, встречи) ===


class EventCreate(BaseModel):
    name: str
    day: date
    start_time: str  # HH:MM
    end_time: str  # HH:MM
    category_id: int | None = None
    task_id: int | None = None
    reminder_before_min: int = 5
    notes: str | None = None


class EventUpdate(BaseModel):
    name: str | None = None
    day: date | None = None
    start_time: str | None = None
    end_time: str | None = None
    category_id: int | None = None
    task_id: int | None = None
    reminder_before_min: int | None = None
    status: str | None = None
    notes: str | None = None


class EventResponse(BaseModel):
    id: int
    name: str
    day: date
    start_time: str
    end_time: str
    category_id: int | None
    task_id: int | None
    reminder_before_min: int
    status: str
    notes: str | None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# === Блоки / Помодоро-сессии (v1.2.0) ===


class BlockCreate(BaseModel):
    """Создание помодоро-блока (обычно автоматическое)."""
    task_id: int | None = None
    day: date
    start_time: str  # HH:MM
    duration_min: int = 25


class BlockUpdate(BaseModel):
    task_id: int | None = None
    status: str | None = None
    notes: str | None = None


class BlockResponse(BaseModel):
    id: int
    task_id: int | None
    day: date
    start_time: str
    duration_min: int
    actual_start_at: datetime | None
    actual_end_at: datetime | None
    actual_duration_min: int | None
    status: str
    pomodoro_number: int
    notes: str | None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class BlockWarning(BaseModel):
    """Предупреждение при создании/обновлении блока."""
    type: str  # overlap, dependency, etc.
    message: str
    details: dict = Field(default_factory=dict)


class BlockCreateResponse(BaseModel):
    block: BlockResponse
    warnings: list[dict] = Field(default_factory=list)


class BlockUpdateResponse(BaseModel):
    block: BlockResponse
    is_active: bool = False


# === Расписание ===


class WeeklyScheduleItem(BaseModel):
    day_of_week: int  # 0=Пн, 6=Вс
    is_day_off: bool = False
    active_from: str = "09:00"  # HH:MM
    active_to: str = "18:00"


class WeeklyScheduleUpdate(BaseModel):
    days: list[WeeklyScheduleItem]


class WeeklyScheduleResponse(BaseModel):
    day_of_week: int
    is_day_off: bool
    active_from: str
    active_to: str

    model_config = {"from_attributes": True}


# === Цели ===


class WeeklyGoalItem(BaseModel):
    category_id: int
    target_hours: float = 0


class WeeklyGoalsUpdate(BaseModel):
    goals: list[WeeklyGoalItem]


class WeeklyGoalResponse(BaseModel):
    category_id: int
    target_hours: float

    model_config = {"from_attributes": True}


# === Статистика ===


class CategoryStatsItem(BaseModel):
    category_id: int
    category_name: str
    category_emoji: str | None
    planned_min: int
    actual_min: int
    target_hours: float


class WeekStatsResponse(BaseModel):
    week_start: str
    # Помодоро-статистика
    pomodoros_done: int = 0
    pomodoros_partial: int = 0
    pomodoros_failed: int = 0
    pomodoros_skipped: int = 0
    pomodoros_total: int = 0
    # Задачи
    tasks_done: int = 0
    tasks_in_progress: int = 0
    tasks_total: int = 0
    # По категориям
    categories: list[CategoryStatsItem]
    total_planned_min: int
    total_actual_min: int
    free_time_min: int
    overload_percent: float
    upcoming_deadlines: list[dict]


# === Allowed Users (для админки) ===


class AllowedUserResponse(BaseModel):
    telegram_id: int
    username: str | None
    first_name: str | None
    is_admin: bool
    is_active: bool
    added_at: datetime | None

    model_config = {"from_attributes": True}


class AddUserRequest(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str | None = None

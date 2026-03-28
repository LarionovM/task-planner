"""Pydantic v2 схемы для API."""

from datetime import date, time, datetime
from pydantic import BaseModel, Field, field_serializer, field_validator


# === Пользователи ===


class UserResponse(BaseModel):
    telegram_id: int
    timezone: str
    quiet_start: str  # HH:MM
    quiet_end: str
    day_start_time: str
    day_end_time: str
    is_admin: bool = False
    is_active: bool = True
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserSettingsUpdate(BaseModel):
    timezone: str | None = None
    quiet_start: str | None = None  # HH:MM
    quiet_end: str | None = None
    day_start_time: str | None = None
    day_end_time: str | None = None


class SpamConfigResponse(BaseModel):
    initial_interval_sec: int
    multiplier: float
    max_interval_sec: int
    enabled: bool
    spam_category_ids: list[int]
    empty_slots_enabled: bool = True
    empty_slots_interval_min: int = 30

    model_config = {"from_attributes": True}


class SpamConfigUpdate(BaseModel):
    initial_interval_sec: int | None = None
    multiplier: float | None = None
    max_interval_sec: int | None = None
    enabled: bool | None = None
    spam_category_ids: list[int] | None = None
    empty_slots_enabled: bool | None = None
    empty_slots_interval_min: int | None = None


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


# === Задачи ===


class TaskCreate(BaseModel):
    name: str
    category_id: int
    minimal_time_min: int = 1
    estimated_time_min: int | None = None
    priority: str = "medium"
    use_pomodoro: bool = False
    is_recurring: bool = False
    recur_days: list[int] = Field(default_factory=list)
    preferred_time: str | None = None  # HH:MM — предпочтительное время для автораспределения
    deadline: date | None = None
    tags: list[str] = Field(default_factory=list)
    depends_on: list[int] = Field(default_factory=list)
    reminder_before_min: int = 5
    allow_grouping: bool = True
    spam_enabled: bool = True
    allow_multi_per_block: bool = False
    device_type: str = "other"  # desktop / mobile / other
    is_epic: bool = False
    epic_id: int | None = None
    epic_emoji: str | None = None

    @field_validator("device_type")
    @classmethod
    def validate_device_type(cls, v: str) -> str:
        if v not in ("desktop", "mobile", "other"):
            raise ValueError("device_type must be desktop, mobile, or other")
        return v


class TaskUpdate(BaseModel):
    name: str | None = None
    category_id: int | None = None
    minimal_time_min: int | None = None
    estimated_time_min: int | None = None
    priority: str | None = None
    use_pomodoro: bool | None = None
    is_recurring: bool | None = None
    recur_days: list[int] | None = None
    preferred_time: str | None = None  # HH:MM
    deadline: date | None = None
    tags: list[str] | None = None
    depends_on: list[int] | None = None
    reminder_before_min: int | None = None
    allow_grouping: bool | None = None
    spam_enabled: bool | None = None
    allow_multi_per_block: bool | None = None
    device_type: str | None = None  # desktop / mobile / other
    is_epic: bool | None = None
    epic_id: int | None = None
    epic_emoji: str | None = None

    @field_validator("device_type")
    @classmethod
    def validate_device_type(cls, v: str | None) -> str | None:
        if v is not None and v not in ("desktop", "mobile", "other"):
            raise ValueError("device_type must be desktop, mobile, or other")
        return v


class TaskResponse(BaseModel):
    id: int
    name: str
    category_id: int
    minimal_time_min: int
    estimated_time_min: int | None
    priority: str
    use_pomodoro: bool
    is_recurring: bool
    recur_days: list[int]
    preferred_time: str | None = None  # HH:MM
    deadline: date | None
    tags: list[str]
    depends_on: list[int]
    reminder_before_min: int
    allow_grouping: bool
    spam_enabled: bool
    allow_multi_per_block: bool = False
    device_type: str = "other"
    is_epic: bool = False
    epic_id: int | None = None
    epic_emoji: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}

    @field_validator("preferred_time", mode="before")
    @classmethod
    def convert_preferred_time(cls, v: time | str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, time):
            return v.strftime("%H:%M")
        return v


class TaskDeleteResponse(BaseModel):
    deleted: bool
    affected_blocks: list[dict] = Field(default_factory=list)


# === Блоки ===


class BlockCreate(BaseModel):
    task_ids: list[int]
    block_name: str | None = None
    day: date
    start_time: str  # HH:MM
    duration_type: str = "fixed"  # fixed / open / range
    duration_min: int | None = None
    min_duration_min: int | None = None
    max_duration_min: int | None = None


class BlockUpdate(BaseModel):
    block_name: str | None = None
    day: date | None = None
    start_time: str | None = None
    duration_type: str | None = None
    duration_min: int | None = None
    min_duration_min: int | None = None
    max_duration_min: int | None = None
    status: str | None = None
    notes: str | None = None


class BlockWarning(BaseModel):
    type: str
    message: str
    block_id: int | None = None


class BlockResponse(BaseModel):
    id: int
    task_ids: list[int]
    block_name: str | None
    day: date
    start_time: str
    duration_type: str
    duration_min: int | None
    min_duration_min: int | None
    max_duration_min: int | None
    actual_start_at: datetime | None
    actual_end_at: datetime | None
    actual_duration_min: int | None
    status: str
    is_mixed: bool
    notes: str | None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class BlockCreateResponse(BaseModel):
    block: BlockResponse
    warnings: list[BlockWarning] = Field(default_factory=list)


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
    blocks_done: int
    blocks_partial: int
    blocks_failed: int
    blocks_skipped: int
    blocks_planned: int
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

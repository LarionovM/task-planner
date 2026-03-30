"""ORM модели — все таблицы базы данных (v1.2.0)."""

from datetime import datetime, date, time

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import relationship

from backend.db.database import Base


class AllowedUser(Base):
    """Белый список пользователей бота."""

    __tablename__ = "allowed_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    added_by = Column(Integer, nullable=True)  # telegram_id админа
    added_at = Column(DateTime, default=func.now(), nullable=False)

    # Связь с настройками пользователя
    user_settings = relationship("User", back_populates="allowed_user", uselist=False)


class User(Base):
    """Настройки пользователя."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(
        Integer,
        ForeignKey("allowed_users.telegram_id"),
        unique=True,
        nullable=False,
        index=True,
    )
    timezone = Column(String(50), default="Europe/Moscow", nullable=False)

    # Рабочий день (без тихого времени — убрано в v1.2.0)
    day_start_time = Column(Time, default=time(8, 0), nullable=False)
    day_end_time = Column(Time, default=time(23, 50), nullable=False)

    # Помодоро настройки
    pomodoro_work_min = Column(Integer, default=25, nullable=False)
    pomodoro_short_break_min = Column(Integer, default=5, nullable=False)
    pomodoro_long_break_min = Column(Integer, default=30, nullable=False)
    pomodoro_cycles_before_long = Column(Integer, default=4, nullable=False)

    # Пауза напоминаний
    reminders_paused_until = Column(DateTime, nullable=True)
    reminders_stopped = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=func.now(), nullable=False)

    allowed_user = relationship("AllowedUser", back_populates="user_settings")
    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="user", cascade="all, delete-orphan")
    task_blocks = relationship("TaskBlock", back_populates="user", cascade="all, delete-orphan")
    weekly_schedule = relationship("WeeklySchedule", back_populates="user", cascade="all, delete-orphan")
    weekly_goals = relationship("WeeklyGoal", back_populates="user", cascade="all, delete-orphan")
    spam_config = relationship("SpamConfig", back_populates="user", uselist=False, cascade="all, delete-orphan")
    logs = relationship("Log", back_populates="user", cascade="all, delete-orphan")


class Category(Base):
    """Категории задач (у каждого пользователя свои)."""

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    emoji = Column(String(10), nullable=True)
    color = Column(String(7), nullable=True)  # hex цвет, напр. #4A90D9
    user_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False, index=True)
    sort_order = Column(Integer, default=0, nullable=False)

    user = relationship("User", back_populates="categories")
    tasks = relationship("Task", back_populates="category")
    events = relationship("Event", back_populates="category")
    weekly_goals = relationship("WeeklyGoal", back_populates="category")


class WeeklySchedule(Base):
    """Расписание рабочей недели."""

    __tablename__ = "weekly_schedule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Пн, 6=Вс
    is_day_off = Column(Boolean, default=False, nullable=False)
    active_from = Column(Time, default=time(9, 0), nullable=False)
    active_to = Column(Time, default=time(18, 0), nullable=False)

    user = relationship("User", back_populates="weekly_schedule")


class WeeklyGoal(Base):
    """Цели по категориям на неделю (в часах)."""

    __tablename__ = "weekly_goals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    target_hours = Column(Float, default=0, nullable=False)

    user = relationship("User", back_populates="weekly_goals")
    category = relationship("Category", back_populates="weekly_goals")


class Task(Base):
    """Задача в бэклоге (v1.2.0 — упрощённая модель)."""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)

    # Прогнозируемое время (минуты) — одно поле вместо minimal + estimated
    estimated_time_min = Column(Integer, nullable=True)

    # Приоритет: high / medium / low
    priority = Column(String(10), default="medium", nullable=False)

    # Статус задачи: grooming / in_progress / blocked / done
    status = Column(String(15), default="grooming", nullable=False, index=True)

    # Повторяемость
    is_recurring = Column(Boolean, default=False, nullable=False)
    recur_days = Column(JSON, default=list)  # [0..6]

    # Назначенная дата (день, без конкретного времени)
    scheduled_date = Column(Date, nullable=True, index=True)

    # Дедлайн
    deadline = Column(Date, nullable=True)

    # Теги и зависимости
    tags = Column(JSON, default=list)  # ["tag1", "tag2"]
    depends_on = Column(JSON, default=list)  # [task_id, ...]

    # Спам
    spam_enabled = Column(Boolean, default=True, nullable=False)

    # Эпики (группировка задач)
    is_epic = Column(Boolean, default=False, nullable=False)
    epic_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    epic_emoji = Column(String(10), nullable=True)

    # Soft delete
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)

    user = relationship("User", back_populates="tasks")
    category = relationship("Category", back_populates="tasks")
    # Связь эпик → подзадачи
    subtasks = relationship("Task", backref="epic", remote_side=[id], foreign_keys=[epic_id])


class Event(Base):
    """Событие в календаре (созвоны, встречи и т.д.) — v1.2.0."""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False, index=True)
    name = Column(String(500), nullable=False)

    # Время
    day = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    # Категория (опционально)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    # Привязка к задаче (опционально)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)

    # Напоминание за N мин (настраиваемое для каждого события)
    reminder_before_min = Column(Integer, default=5, nullable=False)

    # Статус: planned / done / skipped
    status = Column(String(10), default="planned", nullable=False)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    user = relationship("User", back_populates="events")
    category = relationship("Category", back_populates="events")
    task = relationship("Task")


class TaskBlock(Base):
    """Помодоро-сессия (v1.2.0 — упрощённые блоки).

    Теперь блок = одна помодоро-сессия (25+5 мин).
    Привязка к задаче — через выбор пользователя в начале сессии.
    """

    __tablename__ = "task_blocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False, index=True)

    # Привязка к задаче (может быть null — помодоро без задачи)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)

    # День и время
    day = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)

    # Длительность помодоро (берётся из настроек пользователя)
    duration_min = Column(Integer, nullable=False, default=25)

    # Фактическое время
    actual_start_at = Column(DateTime, nullable=True)
    actual_end_at = Column(DateTime, nullable=True)
    actual_duration_min = Column(Integer, nullable=True)

    # Статус: planned / active / done / skipped / failed / partial
    status = Column(String(10), default="planned", nullable=False, index=True)

    # Номер помодоро в цикле (1, 2, 3, 4, 1, 2, ...)
    pomodoro_number = Column(Integer, default=1, nullable=False)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    user = relationship("User", back_populates="task_blocks")
    task = relationship("Task")
    logs = relationship("Log", back_populates="task_block")


class SpamConfig(Base):
    """Настройки спам-напоминаний пользователя."""

    __tablename__ = "spam_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.telegram_id"),
        unique=True,
        nullable=False,
        index=True,
    )
    initial_interval_sec = Column(Integer, default=10, nullable=False)
    multiplier = Column(Float, default=1.5, nullable=False)
    max_interval_sec = Column(Integer, default=600, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    # Категории для которых спам включён (пусто = все)
    spam_category_ids = Column(JSON, default=list)

    user = relationship("User", back_populates="spam_config")


class Log(Base):
    """Логи событий — история действий пользователя."""

    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False, index=True)
    task_block_id = Column(Integer, ForeignKey("task_blocks.id"), nullable=True)

    # Тип события
    event_type = Column(String(30), nullable=False, index=True)
    # pomodoro_start, pomodoro_done, pomodoro_partial, pomodoro_failed,
    # pomodoro_break, pomodoro_resume, pomodoro_skipped,
    # event_reminder, event_start, event_done, event_skipped,
    # spam_started, spam_stopped, day_summary,
    # task_status_changed

    payload = Column(JSON, default=dict)  # причина, комментарий и т.д.
    created_at = Column(DateTime, default=func.now(), nullable=False)

    user = relationship("User", back_populates="logs")
    task_block = relationship("TaskBlock", back_populates="logs")

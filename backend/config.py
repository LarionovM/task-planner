"""Конфигурация приложения из переменных окружения."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из .env файла."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram Bot
    bot_token: str = ""
    admin_user_id: int = 0
    webhook_url: str = ""
    webhook_secret: str = ""

    # База данных
    database_url: str = "sqlite+aiosqlite:///./data/task_planner.db"

    # URLs
    api_base_url: str = "http://localhost:8000/api"
    frontend_url: str = "http://localhost:5173"

    # Настройки
    default_timezone: str = "Europe/Moscow"
    use_polling: bool = True
    debug: bool = True


settings = Settings()


# === Константы ===

# Помодоро (дефолтные значения, пользователь может менять в настройках)
POMODORO_WORK_MIN: int = 25
POMODORO_SHORT_BREAK_MIN: int = 5
POMODORO_LONG_BREAK_MIN: int = 30
POMODORO_CYCLES_BEFORE_LONG: int = 4

# Спам — таймаут перед началом (секунды)
SPAM_QUESTIONNAIRE_TIMEOUT_SEC: int = 120

# Дефолтные параметры спама
DEFAULT_SPAM_INITIAL_INTERVAL_SEC: int = 10
DEFAULT_SPAM_MULTIPLIER: float = 1.5
DEFAULT_SPAM_MAX_INTERVAL_SEC: int = 600

# Тексты спам-сообщений (циклически)
SPAM_TEXTS: list[str] = [
    "эй 👋",
    "ты где?",
    "спим? 😴",
    "просыпайся!",
    "задача ждёт...",
    "не игнорь 😤",
    "время уходит ⏳",
    "ты серьёзно?",
    "ладно... но это твой выбор",
    "ещё один шанс 🔔",
    "я всё ещё здесь 👀",
    "tick tock... ⏰",
]

# Дефолтные категории для нового пользователя
DEFAULT_CATEGORIES: list[dict[str, str]] = [
    {"name": "Работа", "emoji": "💼", "color": "#4A90D9"},
    {"name": "Спорт", "emoji": "🏋️", "color": "#27AE60"},
    {"name": "Обучение", "emoji": "📚", "color": "#8E44AD"},
    {"name": "Личное", "emoji": "❤️", "color": "#E74C3C"},
    {"name": "Отдых", "emoji": "😴", "color": "#F39C12"},
    {"name": "Хобби", "emoji": "🎨", "color": "#1ABC9C"},
]

# Дефолтное расписание недели
# day_of_week: 0=Пн, 6=Вс
DEFAULT_SCHEDULE: list[dict] = [
    {"day_of_week": 0, "is_day_off": False, "active_from": "09:00", "active_to": "18:00"},
    {"day_of_week": 1, "is_day_off": False, "active_from": "09:00", "active_to": "18:00"},
    {"day_of_week": 2, "is_day_off": False, "active_from": "09:00", "active_to": "18:00"},
    {"day_of_week": 3, "is_day_off": False, "active_from": "09:00", "active_to": "18:00"},
    {"day_of_week": 4, "is_day_off": False, "active_from": "09:00", "active_to": "18:00"},
    {"day_of_week": 5, "is_day_off": True, "active_from": "09:00", "active_to": "18:00"},
    {"day_of_week": 6, "is_day_off": True, "active_from": "09:00", "active_to": "18:00"},
]

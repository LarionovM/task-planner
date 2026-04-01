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
DEFAULT_SPAM_MULTIPLIER: float = 1.0
DEFAULT_SPAM_MAX_INTERVAL_SEC: int = 600

# Расширенные тексты спам-сообщений — разные сценарии и настроения
SPAM_TEXTS: list[str] = [
    # Мягкое начало
    "эй 👋",
    "ты где?",
    "алло? 📞",
    "привет, задача ждёт ответа...",
    # Лёгкое беспокойство
    "спим? 😴",
    "ау-у-у 🔊",
    "земля вызывает! 🌍",
    "просыпайся!",
    "задача ждёт...",
    # Нарастающее давление
    "не игнорь 😤",
    "время уходит ⏳",
    "я всё ещё жду ответа...",
    "ты серьёзно?",
    "hello? is it me you're looking for? 🎵",
    "время не останавливается ⏰",
    # Драматичное
    "ладно... но это твой выбор",
    "ещё один шанс 🔔",
    "я всё ещё здесь 👀",
    "tick tock... ⏰",
    "может, всё-таки ответишь?",
    "я начинаю волноваться 😟",
    # Юмор
    "🦗 *тишина*",
    "а задача-то тебя ждала...",
    "бот грустит 🥺",
    "я бы обиделся, но я бот",
    "знаешь, у меня тоже есть чувства... ну, почти",
    "если ты тут — мигни дважды 👁👁",
    # Философское
    "время — единственный невосполнимый ресурс",
    "прокрастинация — вор времени ⏰",
    "каждая минута без ответа — минута без прогресса",
    "дисциплина = свобода 🗽",
    # Мотивация
    "давай, ты же можешь! 💪",
    "один клик — и свобода",
    "просто нажми кнопку, это не сложно",
    "будущий ты скажет спасибо 🙏",
    # Ультиматумы
    "последнее предупреждение... шучу, я буду писать вечно 😈",
    "я могу делать это весь день ⚡",
    "ты не избавишься от меня так просто",
    "сопротивление бесполезно 🤖",
]

# Тексты спама для событий (созвоны, встречи)
SPAM_TEXTS_EVENT: list[str] = [
    "созвон закончился? 📞",
    "встреча всё ещё идёт? 🤔",
    "если созвон окончен — нажми «Завершить» ✅",
    "ау, вернулся с созвона? 👋",
    "мне кажется, или созвон затянулся? ⏰",
    "надеюсь, встреча была продуктивной! Завершай 🙂",
    "бот ждёт тебя после созвона...",
    "не забудь отметить завершение встречи!",
    "тебя там не захватили? 😅",
    "я тут заждался, пока ты на созвоне... ⏳",
]

# Тексты для конца дня (невыполненные задачи)
SPAM_TEXTS_EOD: list[str] = [
    "день заканчивается, а задачи остались... 📋",
    "перенести незавершённое на завтра? 🔄",
    "не все задачи выполнены — это нормально, главное не забыть про них",
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

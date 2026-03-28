"""Обработчики /start и /help."""

import logging

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from backend.config import settings
from backend.db.database import async_session
from backend.db.crud.users import get_or_create_user
from backend.db.models import AllowedUser, User

logger = logging.getLogger(__name__)

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, allowed_user: AllowedUser):
    """Команда /start — приветствие + кнопка открыть планировщик."""
    async with async_session() as session:
        user = await get_or_create_user(session, allowed_user.telegram_id)
        await session.commit()

    # Кнопка Web App (только HTTPS) или ссылка для localhost
    frontend_url = settings.frontend_url
    if frontend_url.startswith("https://"):
        webapp_button = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📅 Открыть планировщик",
                web_app=WebAppInfo(url=frontend_url),
            )],
        ])
    else:
        # Локальная разработка — обычная ссылка (Web App требует HTTPS)
        webapp_button = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📅 Открыть планировщик (localhost)",
                url=frontend_url,
            )],
        ])

    # Проверяем первый ли это запуск (есть ли timezone отличный от дефолта)
    is_first_launch = user.timezone == settings.default_timezone

    if is_first_launch:
        # Первый запуск — приветствие с описанием
        text = (
            "👋 *Привет! Я — Task Planner Bot*\n\n"
            "Я помогу тебе планировать день и не забывать о задачах.\n\n"
            "🔹 *Что я умею:*\n"
            "• 📋 Бэклог задач с приоритетами и категориями\n"
            "• 📅 Недельный календарь с drag & drop\n"
            "• ⏰ Умные напоминания о начале и конце блоков\n"
            "• 🍅 Pomodoro-таймер (25+5 мин)\n"
            "• 📊 Статистика и цели по категориям\n"
            "• 😤 Настойчивый спам если игнорируешь задачу\n\n"
            "👇 *Нажми кнопку ниже* чтобы открыть планировщик и настроить расписание.\n"
            "Или набери /help для списка команд."
        )
    else:
        # Уже настроен — краткое приветствие
        text = (
            f"👋 *С возвращением!*\n\n"
            f"🕐 Часовой пояс: {user.timezone}\n"
            f"🔇 Тихое время: {user.quiet_start.strftime('%H:%M')}–{user.quiet_end.strftime('%H:%M')}\n\n"
            "👇 Нажми кнопку чтобы открыть планировщик."
        )

    await message.answer(text, reply_markup=webapp_button, parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: Message, allowed_user: AllowedUser):
    """Команда /help — справка по командам."""
    text = (
        "📖 *Справка по командам*\n\n"
        "/start — Открыть планировщик\n"
        "/help — Эта справка\n"
        "/plan — План на день\n"
        "  • `/plan` — на сегодня\n"
        "  • `/plan завтра` — на завтра\n"
        "  • `/plan 2` — через 2 дня\n"
        "  • `/plan неделя` — на всю неделю\n"
        "/next — Ближайший блок\n"
        "/settings — Настройки: часовой пояс, тихое время, спам\n"
        "/stats — Статистика за неделю\n"
        "/stop — Остановить все напоминания\n"
        "/pause <время> — Пауза напоминаний\n"
        "  • `/pause 30m` — на 30 минут\n"
        "  • `/pause 2h` — на 2 часа\n"
        "  • `/pause 1d` — на день\n"
        "  • `/pause 18:00` — до указанного времени\n"
        "/resume — Возобновить напоминания\n"
    )

    if allowed_user.is_admin:
        text += "\n🔑 *Админ-команды:*\n/admin — Панель администратора\n"

    await message.answer(text, parse_mode="Markdown")

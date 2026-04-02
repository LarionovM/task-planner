"""Обработчики /start и /help (v1.2.0)."""

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


def _webapp_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой Web App."""
    frontend_url = settings.frontend_url
    if frontend_url.startswith("https://"):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📅 Открыть планировщик",
                web_app=WebAppInfo(url=frontend_url),
            )],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📅 Открыть планировщик (localhost)",
                url=frontend_url,
            )],
        ])


@router.message(CommandStart())
async def cmd_start(message: Message, allowed_user: AllowedUser):
    """Команда /start — приветствие + кнопка открыть планировщик."""
    async with async_session() as session:
        user = await get_or_create_user(session, allowed_user.telegram_id)
        await session.commit()

    # Проверяем первый ли это запуск
    is_first_launch = user.timezone == settings.default_timezone

    if is_first_launch:
        text = (
            "👋 *Привет! Я — Task Planner Bot*\n\n"
            "Я помогу тебе планировать день с помощью метода фокус-сессий.\n\n"
            "🔹 *Что я умею:*\n"
            "• 🍅 Автоматические циклы фокуса весь рабочий день\n"
            "• 📋 Бэклог задач с приоритетами и статусами\n"
            "• 📅 Календарь с событиями (созвоны, встречи)\n"
            "• ⏰ Уведомления о старте и конце сессий фокуса\n"
            "• 📊 Статистика по задачам и сессиям фокуса\n"
            "• 😤 Настойчивый спам если игнорируешь\n\n"
            "👇 *Нажми кнопку ниже* чтобы открыть планировщик.\n"
            "Или набери /help для списка команд."
        )
    else:
        text = (
            f"👋 *С возвращением!*\n\n"
            f"🕐 Часовой пояс: {user.timezone}\n"
            f"🍅 Фокус: {user.pomodoro_work_min or 25} мин работа / "
            f"{user.pomodoro_short_break_min or 5} мин перерыв\n\n"
            "👇 Нажми кнопку чтобы открыть планировщик."
        )

    await message.answer(text, reply_markup=_webapp_keyboard(), parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: Message, allowed_user: AllowedUser):
    """Команда /help — справка по командам."""
    text = (
        "📖 *Справка по командам*\n\n"
        "/start — Открыть планировщик\n"
        "/help — Эта справка\n"
        "/plan — План на сегодня (задачи + события)\n"
        "/backlog — Список задач, смена статусов\n"
        "/settings — Настройки, пауза, стоп напоминаний\n"
        "/stats — Статистика за неделю\n"
    )

    if allowed_user.is_admin:
        text += "\n🔑 *Админ:* доступно в /settings\n"

    await message.answer(text, parse_mode="Markdown")

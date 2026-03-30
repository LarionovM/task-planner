"""Инициализация Telegram бота — Bot, Dispatcher, роутеры (v1.2.0)."""

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from backend.config import settings as app_settings
from backend.bot.middlewares import WhitelistMiddleware
from backend.bot.handlers import start, admin, callbacks, plan, backlog
from backend.bot.handlers import settings as settings_handlers

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    """Создаёт экземпляр бота."""
    return Bot(
        token=app_settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )


def create_dispatcher() -> Dispatcher:
    """Создаёт диспетчер с роутерами и middleware."""
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрируем whitelist middleware на все типы событий
    dp.message.outer_middleware(WhitelistMiddleware())
    dp.callback_query.outer_middleware(WhitelistMiddleware())

    # Подключаем роутеры (порядок важен: более специфичные сначала)
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(settings_handlers.router)
    dp.include_router(plan.router)
    dp.include_router(backlog.router)
    dp.include_router(callbacks.router)  # Общие callback-и последними

    return dp


async def set_bot_commands(bot: Bot) -> None:
    """Регистрирует команды бота в Telegram (v1.2.0)."""
    commands = [
        BotCommand(command="start", description="Открыть планировщик"),
        BotCommand(command="help", description="Справка по командам"),
        BotCommand(command="plan", description="План на сегодня"),
        BotCommand(command="backlog", description="Список задач, статусы"),
        BotCommand(command="settings", description="Настройки, пауза, стоп"),
        BotCommand(command="stats", description="Статистика за неделю"),
    ]
    await bot.set_my_commands(commands)
    logger.info("Команды бота зарегистрированы (v1.2.0)")

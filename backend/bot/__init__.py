"""Инициализация Telegram бота — Bot, Dispatcher, роутеры."""

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from backend.config import settings as app_settings
from backend.bot.middlewares import WhitelistMiddleware
from backend.bot.handlers import start, admin, controls, callbacks, plan
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

    # Подключаем роутеры
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(controls.router)
    dp.include_router(settings_handlers.router)
    dp.include_router(plan.router)
    dp.include_router(callbacks.router)

    return dp


async def set_bot_commands(bot: Bot) -> None:
    """Регистрирует команды бота в Telegram."""
    commands = [
        BotCommand(command="start", description="Открыть планировщик"),
        BotCommand(command="help", description="Справка по командам"),
        BotCommand(command="plan", description="План на день"),
        BotCommand(command="next", description="Ближайшая задача"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="stats", description="Статистика за неделю"),
        BotCommand(command="stop", description="Остановить напоминания"),
        BotCommand(command="pause", description="Пауза напоминаний"),
        BotCommand(command="resume", description="Возобновить напоминания"),
    ]
    await bot.set_my_commands(commands)
    logger.info("Команды бота зарегистрированы")

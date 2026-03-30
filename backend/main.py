"""Точка входа — FastAPI приложение + Telegram бот."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from aiogram.types import Update

from backend.config import settings
from backend.db.database import init_db, async_session
from backend.db.crud.users import ensure_admin_exists
from backend.api.routes import users, categories, tasks, blocks, events, schedule, goals, stats
from backend.bot import create_bot, create_dispatcher, set_bot_commands
from backend.bot.scheduler import init_scheduler, restore_jobs_on_startup, scheduler

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Приглушаем шумные логгеры
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные объекты бота
bot = create_bot()
dp = create_dispatcher()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация при старте, очистка при остановке."""
    # === Старт ===
    logger.info("Запуск приложения...")

    # Инициализируем БД
    await init_db()

    # Создаём админа если не существует
    async with async_session() as session:
        await ensure_admin_exists(session)
        await session.commit()

    # Регистрируем команды бота
    await set_bot_commands(bot)

    # Инициализируем scheduler
    init_scheduler(bot)

    # Восстанавливаем jobs из БД
    await restore_jobs_on_startup()

    # Рассылка уведомлений о новой версии
    from backend.bot.version_notify import notify_new_version
    sent = await notify_new_version(bot)
    if sent:
        logger.info(f"Отправлено {sent} уведомлений о новой версии")

    # Запускаем бота
    if settings.use_polling:
        # Polling режим (локальная разработка)
        logger.info("Запуск бота в режиме polling...")
        polling_task = asyncio.create_task(_start_polling())
    else:
        # Webhook режим (продакшен)
        logger.info("Настройка webhook...")
        await bot.set_webhook(
            url=settings.webhook_url,
            secret_token=settings.webhook_secret,
            drop_pending_updates=True,
        )

    logger.info("Приложение готово!")
    yield

    # === Остановка ===
    logger.info("Остановка приложения...")
    scheduler.shutdown(wait=False)
    if settings.use_polling:
        await dp.stop_polling()
    else:
        await bot.delete_webhook()
    await bot.session.close()


async def _start_polling():
    """Запускает polling в фоне."""
    try:
        await dp.start_polling(bot, handle_signals=False)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Ошибка polling: {e}")


app = FastAPI(
    title="Task Planner Bot API",
    version="1.2.0",
    lifespan=lifespan,
)

# CORS — разрешаем фронтенд (в продакшене только FRONTEND_URL, в dev ещё localhost)
_cors_origins = [settings.frontend_url]
if settings.debug:
    _cors_origins += ["http://localhost:5173", "http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем API роутеры
app.include_router(users.router)
app.include_router(categories.router)
app.include_router(tasks.router)
app.include_router(blocks.router)
app.include_router(events.router)
app.include_router(schedule.router)
app.include_router(goals.router)
app.include_router(stats.router)


@app.get("/api/health")
async def health():
    """Проверка что сервер жив."""
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request) -> Response:
    """Обработка webhook от Telegram."""
    # Проверяем секретный токен
    if settings.webhook_secret:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret != settings.webhook_secret:
            return Response(status_code=403)

    # Обрабатываем апдейт
    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot=bot, update=update)
    return Response(status_code=200)

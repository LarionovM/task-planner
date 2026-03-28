"""Обработчики /stop, /pause, /resume."""

import logging
import re
from datetime import datetime, timedelta, time

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from backend.db.database import async_session
from backend.db.crud.users import get_or_create_user
from backend.db.models import AllowedUser

logger = logging.getLogger(__name__)

router = Router()

# Хранилище состояний паузы/стопа (в памяти)
# {telegram_id: {"stopped": bool, "paused_until": datetime | None}}
_user_reminder_state: dict[int, dict] = {}


def is_reminders_active(telegram_id: int) -> bool:
    """Проверяет активны ли напоминания для пользователя."""
    state = _user_reminder_state.get(telegram_id, {})
    if state.get("stopped", False):
        return False
    paused_until = state.get("paused_until")
    if paused_until and datetime.now() < paused_until:
        return False
    return True


def get_reminder_state(telegram_id: int) -> dict:
    """Возвращает состояние напоминаний."""
    return _user_reminder_state.get(telegram_id, {})


@router.message(Command("stop"))
async def cmd_stop(message: Message, allowed_user: AllowedUser):
    """Остановить все напоминания."""
    _user_reminder_state[allowed_user.telegram_id] = {
        "stopped": True,
        "paused_until": None,
    }
    await message.answer(
        "🔇 Напоминания отключены.\n"
        "Чтобы включить обратно — /resume"
    )


@router.message(Command("resume"))
async def cmd_resume(message: Message, allowed_user: AllowedUser):
    """Возобновить напоминания."""
    _user_reminder_state[allowed_user.telegram_id] = {
        "stopped": False,
        "paused_until": None,
    }
    await message.answer("✅ Напоминания включены!")


@router.message(Command("pause"))
async def cmd_pause(message: Message, allowed_user: AllowedUser):
    """Пауза напоминаний на указанное время."""
    # Парсим аргумент
    text = message.text or ""
    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        # По умолчанию — пауза на 30 минут
        arg = "30m"
    else:
        arg = parts[1].strip().lower()
    now = datetime.now()
    until: datetime | None = None

    # Парсим HH:MM (с опциональным "до" для обратной совместимости)
    time_arg = arg
    if time_arg.startswith("до ") or time_arg.startswith("до\xa0"):
        time_arg = time_arg[3:].strip()

    time_match = re.match(r"^(\d{1,2}):(\d{2})$", time_arg)
    if time_match:
        h, m = int(time_match.group(1)), int(time_match.group(2))
        until = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if until <= now:
            # Если время уже прошло — на завтра
            until += timedelta(days=1)

    # Парсим "30m", "2h", "1d"
    if until is None:
        match = re.match(r"(\d+)\s*(m|min|h|hour|d|day)s?", arg)
        if match:
            value = int(match.group(1))
            unit = match.group(2)[0]  # m, h, d
            if unit == "m":
                until = now + timedelta(minutes=value)
            elif unit == "h":
                until = now + timedelta(hours=value)
            elif unit == "d":
                until = now + timedelta(days=value)

    if until is None:
        await message.answer(
            "❌ Не удалось распознать время.\n"
            "Примеры: `30m`, `2h`, `1d`, `18:00`",
            parse_mode="Markdown",
        )
        return

    _user_reminder_state[allowed_user.telegram_id] = {
        "stopped": False,
        "paused_until": until,
    }

    until_str = until.strftime("%H:%M %d.%m")
    await message.answer(f"⏸ Пауза до {until_str}\n/resume чтобы возобновить раньше")

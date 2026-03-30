"""Обработчики inline-кнопок: завершить помодоро, опросник, причины (v1.2.0)."""

import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from backend.db.database import async_session
from backend.db.crud.blocks import get_block, create_log
from backend.db.models import AllowedUser

logger = logging.getLogger(__name__)

router = Router()


class ReasonStates(StatesGroup):
    """FSM для ввода причины «Другое»."""
    waiting_reason = State()


# === Завершить помодоро/блок ===


@router.callback_query(F.data.startswith("block_finish:"))
async def cb_block_finish(callback: CallbackQuery, allowed_user: AllowedUser):
    """Кнопка «✅ Завершить» — завершение помодоро-блока."""
    block_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        block = await get_block(session, block_id, allowed_user.telegram_id)
        if not block or block.status != "active":
            await callback.answer("Блок уже не активен", show_alert=True)
            return

        now = datetime.now()
        block.status = "done"
        block.actual_end_at = now
        if block.actual_start_at:
            block.actual_duration_min = int(
                (now - block.actual_start_at).total_seconds() / 60
            )

        await create_log(session, allowed_user.telegram_id, "block_done",
                         task_block_id=block_id,
                         payload={"actual_duration_min": block.actual_duration_min})
        await session.commit()

    # Показываем опросник
    await _send_questionnaire(callback, block_id)
    await callback.answer("Помодоро завершён!")


@router.callback_query(F.data.startswith("block_skip:"))
async def cb_block_skip(callback: CallbackQuery, allowed_user: AllowedUser):
    """Кнопка «⏭ Пропустить» — пропуск помодоро."""
    block_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        block = await get_block(session, block_id, allowed_user.telegram_id)
        if not block:
            await callback.answer("Блок не найден", show_alert=True)
            return

        block.status = "skipped"
        await create_log(session, allowed_user.telegram_id, "block_skipped",
                         task_block_id=block_id)
        await session.commit()

    await callback.message.edit_text("⏭ Помодоро пропущен.")
    await callback.answer()


# === Опросник: Выполнено / Частично / Не выполнено ===


async def _send_questionnaire(callback: CallbackQuery, block_id: int):
    """Показать опросник завершения помодоро."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выполнено", callback_data=f"quest_done:{block_id}"),
            InlineKeyboardButton(text="⚡ Частично", callback_data=f"quest_partial:{block_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ Не выполнено", callback_data=f"quest_failed:{block_id}"),
        ],
    ])
    await callback.message.edit_text(
        "🏁 *Помодоро завершён!*\nКак прошло?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


def questionnaire_keyboard(block_id: int) -> InlineKeyboardMarkup:
    """Клавиатура опросника (для использования из reminders.py)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выполнено", callback_data=f"quest_done:{block_id}"),
            InlineKeyboardButton(text="⚡ Частично", callback_data=f"quest_partial:{block_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ Не выполнено", callback_data=f"quest_failed:{block_id}"),
        ],
    ])


@router.callback_query(F.data.startswith("quest_done:"))
async def cb_quest_done(callback: CallbackQuery, allowed_user: AllowedUser):
    """Помодоро выполнен полностью."""
    block_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        block = await get_block(session, block_id, allowed_user.telegram_id)
        if block:
            block.status = "done"
            await create_log(session, allowed_user.telegram_id, "block_done",
                             task_block_id=block_id)
            await session.commit()

    # Останавливаем спам если был
    await _stop_spam_safe(allowed_user.telegram_id)

    await callback.message.edit_text(
        "✅ *Выполнено!* Отлично, так держать! 💪",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quest_partial:"))
async def cb_quest_partial(callback: CallbackQuery, allowed_user: AllowedUser):
    """Помодоро выполнен частично — спрашиваем причину."""
    block_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        block = await get_block(session, block_id, allowed_user.telegram_id)
        if block:
            block.status = "partial"
            await create_log(session, allowed_user.telegram_id, "block_partial",
                             task_block_id=block_id)
            await session.commit()

    await _stop_spam_safe(allowed_user.telegram_id)

    # Спрашиваем причину
    keyboard = _reason_keyboard(block_id)
    await callback.message.edit_text(
        "⚡ *Частично выполнено*\nЧто помешало?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quest_failed:"))
async def cb_quest_failed(callback: CallbackQuery, allowed_user: AllowedUser):
    """Помодоро не выполнен — спрашиваем причину."""
    block_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        block = await get_block(session, block_id, allowed_user.telegram_id)
        if block:
            block.status = "failed"
            await create_log(session, allowed_user.telegram_id, "block_failed",
                             task_block_id=block_id)
            await session.commit()

    await _stop_spam_safe(allowed_user.telegram_id)

    keyboard = _reason_keyboard(block_id)
    await callback.message.edit_text(
        "❌ *Не выполнено*\nЧто помешало?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    await callback.answer()


# === Причины ===


def _reason_keyboard(block_id: int) -> InlineKeyboardMarkup:
    """Клавиатура причин невыполнения."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏰ Не успел", callback_data=f"reason:no_time:{block_id}"),
            InlineKeyboardButton(text="🌀 Отвлёкся", callback_data=f"reason:distracted:{block_id}"),
        ],
        [
            InlineKeyboardButton(text="🚫 Неактуально", callback_data=f"reason:irrelevant:{block_id}"),
            InlineKeyboardButton(text="📝 Другое", callback_data=f"reason:other:{block_id}"),
        ],
    ])


@router.callback_query(F.data.startswith("reason:"))
async def cb_reason(callback: CallbackQuery, state: FSMContext, allowed_user: AllowedUser):
    """Обработка причины невыполнения."""
    parts = callback.data.split(":")
    reason_type = parts[1]
    block_id = int(parts[2])

    reason_texts = {
        "no_time": "Не успел",
        "distracted": "Отвлёкся",
        "irrelevant": "Неактуально",
    }

    if reason_type == "other":
        # Просим ввести причину
        await state.set_state(ReasonStates.waiting_reason)
        await state.update_data(block_id=block_id)
        await callback.message.edit_text("📝 Напиши причину:")
        await callback.answer()
        return

    reason = reason_texts.get(reason_type, reason_type)

    async with async_session() as session:
        await create_log(session, allowed_user.telegram_id, "block_reason",
                         task_block_id=block_id,
                         payload={"reason": reason})
        await session.commit()

    await callback.message.edit_text(
        f"📝 Понял: _{reason}_\nВ следующий раз получится лучше! 💪",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(ReasonStates.waiting_reason, ~F.text.startswith("/"))
async def process_other_reason(message: Message, state: FSMContext, allowed_user: AllowedUser):
    """Обработка произвольной причины."""
    data = await state.get_data()
    block_id = data.get("block_id")
    reason = message.text or "не указана"

    async with async_session() as session:
        await create_log(session, allowed_user.telegram_id, "block_reason",
                         task_block_id=block_id,
                         payload={"reason": reason})
        await session.commit()

    await message.answer(
        f"📝 Записал: _{reason}_\nВ следующий раз получится лучше! 💪",
        parse_mode="Markdown",
    )
    await state.clear()


# === Обработка любого сообщения от пользователя во время спама ===


@router.message(F.text, ~F.text.startswith("/"))
async def handle_user_message_during_spam(message: Message, allowed_user: AllowedUser):
    """Если пользователь написал что-то во время спама — остановить спам и показать опросник."""
    from backend.bot.reminders import _spam_tasks, _spam_messages

    user_id = allowed_user.telegram_id

    if user_id in _spam_tasks:
        await _stop_spam_safe(user_id)

        # Находим последний активный блок пользователя
        async with async_session() as session:
            from sqlalchemy import select
            from backend.db.models import TaskBlock
            result = await session.execute(
                select(TaskBlock).where(
                    TaskBlock.user_id == user_id,
                    TaskBlock.status == "active",
                ).order_by(TaskBlock.id.desc())
            )
            active_block = result.scalars().first()

        if active_block:
            keyboard = questionnaire_keyboard(active_block.id)
            await message.answer(
                "🏁 *Помодоро завершён!*\nКак прошло?",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )


# === Утилиты ===


async def _stop_spam_safe(user_id: int):
    """Безопасно остановить спам (с обработкой ошибок импорта)."""
    try:
        from backend.bot.reminders import stop_spam_and_cleanup
        await stop_spam_and_cleanup(user_id)
    except (ImportError, Exception) as e:
        logger.warning(f"Не удалось остановить спам для {user_id}: {e}")

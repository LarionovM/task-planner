"""Обработчики inline-кнопок: завершить блок, опросник, причины."""

import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
    Message,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from backend.db.database import async_session
from backend.db.crud.blocks import get_block, create_log
from backend.db.models import AllowedUser
from backend.bot.reminders import (
    stop_spam_and_cleanup,
    send_block_end_questionnaire,
)
from backend.bot.scheduler import cancel_block_jobs

logger = logging.getLogger(__name__)

router = Router()


class ReasonStates(StatesGroup):
    """FSM для ввода причины «Другое»."""
    waiting_reason = State()


# === Завершить блок ===


@router.callback_query(F.data.startswith("block_finish:"))
async def cb_block_finish(callback: CallbackQuery, allowed_user: AllowedUser):
    """Кнопка «✅ Завершить» — для open и range блоков (в рамках диапазона)."""
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

    # Отменяем оставшиеся jobs
    cancel_block_jobs(block_id)

    # Останавливаем спам если был
    await stop_spam_and_cleanup(allowed_user.telegram_id)

    # Показываем опросник
    await send_block_end_questionnaire(block_id)
    await callback.answer("Блок завершён!")


@router.callback_query(F.data.startswith("block_finish_early:"))
async def cb_block_finish_early(callback: CallbackQuery, allowed_user: AllowedUser):
    """Кнопка «⏹ Завершить досрочно» — для fixed и range блоков."""
    block_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        block = await get_block(session, block_id, allowed_user.telegram_id)
        if not block or block.status != "active":
            await callback.answer("Блок уже не активен", show_alert=True)
            return

        now = datetime.now()
        block.actual_end_at = now
        if block.actual_start_at:
            block.actual_duration_min = int(
                (now - block.actual_start_at).total_seconds() / 60
            )

        await create_log(session, allowed_user.telegram_id, "block_finished_early",
                         task_block_id=block_id,
                         payload={"actual_duration_min": block.actual_duration_min})
        await session.commit()

    # Отменяем оставшиеся jobs (включая scheduled end)
    cancel_block_jobs(block_id)

    # Показываем опросник
    await send_block_end_questionnaire(block_id)
    await callback.answer("Блок завершён досрочно")


# === Опросник: Выполнено / Частично / Не выполнено ===


@router.callback_query(F.data.startswith("quest_done:"))
async def cb_quest_done(callback: CallbackQuery, allowed_user: AllowedUser):
    """Блок выполнен полностью."""
    block_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        block = await get_block(session, block_id, allowed_user.telegram_id)
        if block:
            block.status = "done"
            await create_log(session, allowed_user.telegram_id, "block_done",
                             task_block_id=block_id)
            await session.commit()

    await stop_spam_and_cleanup(allowed_user.telegram_id)
    cancel_block_jobs(block_id)

    await callback.message.edit_text(
        f"✅ *Выполнено!* Отлично, так держать! 💪",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quest_partial:"))
async def cb_quest_partial(callback: CallbackQuery, allowed_user: AllowedUser):
    """Блок выполнен частично — спрашиваем причину."""
    block_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        block = await get_block(session, block_id, allowed_user.telegram_id)
        if block:
            block.status = "partial"
            await create_log(session, allowed_user.telegram_id, "block_partial",
                             task_block_id=block_id)
            await session.commit()

    await stop_spam_and_cleanup(allowed_user.telegram_id)
    cancel_block_jobs(block_id)

    # Спрашиваем причину
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏰ Не успел", callback_data=f"reason:no_time:{block_id}"),
            InlineKeyboardButton(text="🌀 Отвлёкся", callback_data=f"reason:distracted:{block_id}"),
        ],
        [
            InlineKeyboardButton(text="🚫 Неактуально", callback_data=f"reason:irrelevant:{block_id}"),
            InlineKeyboardButton(text="📝 Другое", callback_data=f"reason:other:{block_id}"),
        ],
    ])

    await callback.message.edit_text(
        "⚡ *Частично выполнено*\nЧто помешало?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quest_failed:"))
async def cb_quest_failed(callback: CallbackQuery, allowed_user: AllowedUser):
    """Блок не выполнен — спрашиваем причину."""
    block_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        block = await get_block(session, block_id, allowed_user.telegram_id)
        if block:
            block.status = "failed"
            await create_log(session, allowed_user.telegram_id, "block_failed",
                             task_block_id=block_id)
            await session.commit()

    await stop_spam_and_cleanup(allowed_user.telegram_id)
    cancel_block_jobs(block_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏰ Не успел", callback_data=f"reason:no_time:{block_id}"),
            InlineKeyboardButton(text="🌀 Отвлёкся", callback_data=f"reason:distracted:{block_id}"),
        ],
        [
            InlineKeyboardButton(text="🚫 Неактуально", callback_data=f"reason:irrelevant:{block_id}"),
            InlineKeyboardButton(text="📝 Другое", callback_data=f"reason:other:{block_id}"),
        ],
    ])

    await callback.message.edit_text(
        "❌ *Не выполнено*\nЧто помешало?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    await callback.answer()


# === Причины ===


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
        await callback.message.edit_text(
            "📝 Напиши причину:",
        )
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
    """Если пользователь написал что-то во время спама — остановить спам и показать опросник.
    Не перехватываем команды (начинающиеся с /)."""
    from backend.bot.reminders import _spam_tasks, _spam_messages

    user_id = allowed_user.telegram_id

    if user_id in _spam_tasks:
        # Останавливаем спам, удаляем сообщения
        await stop_spam_and_cleanup(user_id)

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
            await send_block_end_questionnaire(active_block.id)

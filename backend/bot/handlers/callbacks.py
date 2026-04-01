"""Обработчики inline-кнопок: помодоро, события, опросник, причины (v1.2.0)."""

import logging
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

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
from backend.db.crud.tasks import get_task, get_tasks_for_today, update_task
from backend.db.models import AllowedUser, TaskBlock, Event
from backend.bot.reminders import stop_pomo_pick_spam, stop_spam_and_cleanup

logger = logging.getLogger(__name__)

router = Router()


class ReasonStates(StatesGroup):
    """FSM для ввода причины «Другое»."""
    waiting_reason = State()


# === Помодоро: выбор задачи ===


@router.callback_query(F.data.startswith("pomo:task:"))
async def cb_pomo_select_task(callback: CallbackQuery, allowed_user: AllowedUser):
    """Пользователь выбрал задачу для помодоро."""
    stop_pomo_pick_spam(allowed_user.telegram_id)
    try:
        parts = callback.data.split(":")
        task_id = int(parts[2])
        pomo_number = int(parts[3])

        from backend.db.crud.users import get_or_create_user
        async with async_session() as session:
            user = await get_or_create_user(session, allowed_user.telegram_id)
            task = await get_task(session, task_id, allowed_user.telegram_id)

            if not task:
                await callback.answer("Задача не найдена", show_alert=True)
                return

            work_min = user.pomodoro_work_min or 25
            tz = ZoneInfo(user.timezone or "Europe/Moscow")
            now = datetime.now(tz)

            # Создаём помодоро-блок с привязкой к задаче
            block = TaskBlock(
                user_id=allowed_user.telegram_id,
                task_id=task_id,
                day=now.date(),
                start_time=now.time(),
                duration_min=work_min,
                status="active",
                pomodoro_number=pomo_number,
                actual_start_at=datetime.now(),
            )
            session.add(block)

            # Меняем статус задачи на in_progress если была grooming
            if task.status == "grooming":
                task.status = "in_progress"

            await create_log(session, allowed_user.telegram_id, "block_active",
                             task_block_id=None,
                             payload={"task_id": task_id, "pomodoro_number": pomo_number})
            await session.commit()
            block_id = block.id

        # Формируем сообщение с описанием и ссылкой
        text_lines = [f"🍅 *Помодоро #{pomo_number}* — {work_min} мин"]
        text_lines.append(f"📝 {task.name}")

        description = getattr(task, 'description', None)
        link = getattr(task, 'link', None)
        if description:
            text_lines.append(f"📄 _{description}_")
        if link:
            text_lines.append(f"🔗 {link}")

        text_lines.append("\nФокус! 🎯")

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Завершить",
                callback_data=f"block_finish:{block_id}",
            )],
        ])

        await callback.message.edit_text(
            "\n".join(text_lines),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в cb_pomo_select_task: {e}", exc_info=True)
        await callback.answer(str(e)[:190], show_alert=True)


@router.callback_query(F.data.startswith("pomo:notask:"))
async def cb_pomo_no_task(callback: CallbackQuery, allowed_user: AllowedUser):
    """Помодоро без привязки к задаче."""
    stop_pomo_pick_spam(allowed_user.telegram_id)
    try:
        pomo_number = int(callback.data.split(":")[2])

        from backend.db.crud.users import get_or_create_user
        async with async_session() as session:
            user = await get_or_create_user(session, allowed_user.telegram_id)
            work_min = user.pomodoro_work_min or 25
            tz = ZoneInfo(user.timezone or "Europe/Moscow")
            now = datetime.now(tz)

            block = TaskBlock(
                user_id=allowed_user.telegram_id,
                task_id=None,
                day=now.date(),
                start_time=now.time(),
                duration_min=work_min,
                status="active",
                pomodoro_number=pomo_number,
                actual_start_at=datetime.now(),
            )
            session.add(block)
            await create_log(session, allowed_user.telegram_id, "block_active",
                             payload={"pomodoro_number": pomo_number, "no_task": True})
            await session.commit()
            block_id = block.id

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Завершить",
                callback_data=f"block_finish:{block_id}",
            )],
        ])

        await callback.message.edit_text(
            f"🍅 *Помодоро #{pomo_number}* — {work_min} мин\nФокус без задачи! 🎯",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в cb_pomo_no_task: {e}", exc_info=True)
        await callback.answer(f"Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("pomo:skip:"))
async def cb_pomo_skip(callback: CallbackQuery, allowed_user: AllowedUser):
    """Пропуск помодоро."""
    stop_pomo_pick_spam(allowed_user.telegram_id)
    try:
        pomo_number = int(callback.data.split(":")[2])

        async with async_session() as session:
            await create_log(session, allowed_user.telegram_id, "block_skipped",
                             payload={"pomodoro_number": pomo_number})
            await session.commit()

        await callback.message.edit_text(f"⏭ Помодоро #{pomo_number} пропущен.")
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в cb_pomo_skip: {e}", exc_info=True)
        await callback.answer(f"Ошибка: {e}", show_alert=True)


# === Завершение события ===


@router.callback_query(F.data.startswith("event:finish:"))
async def cb_event_finish(callback: CallbackQuery, allowed_user: AllowedUser):
    """Кнопка «✅ Завершить событие»."""
    try:
        event_id = int(callback.data.split(":")[2])

        async with async_session() as session:
            from sqlalchemy import select
            result = await session.execute(select(Event).where(Event.id == event_id))
            event = result.scalar_one_or_none()

            if not event:
                await callback.answer("Событие не найдено", show_alert=True)
                return

            if event.status == "done":
                await callback.answer("Уже завершено", show_alert=True)
                return

            event.status = "done"
            await create_log(session, allowed_user.telegram_id, "event_finished",
                             payload={"event_id": event_id, "event_name": event.name})
            await session.commit()

        # Останавливаем спам если был
        await _stop_spam_safe(allowed_user.telegram_id)

        from backend.bot.scheduler import cancel_event_jobs
        cancel_event_jobs(event_id)

        await callback.message.edit_text(
            f"✅ Событие *{event.name}* завершено!",
            parse_mode="Markdown",
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в cb_event_finish: {e}", exc_info=True)
        await callback.answer(f"Ошибка: {e}", show_alert=True)


# === Перенос задач (итог дня) ===


@router.callback_query(F.data.startswith("eod:reschedule:"))
async def cb_eod_reschedule(callback: CallbackQuery, allowed_user: AllowedUser):
    """Перенос незавершённых задач на указанную дату."""
    target_date_str = callback.data.split(":")[2]
    target_date = date.fromisoformat(target_date_str)

    async with async_session() as session:
        from backend.db.crud.users import get_or_create_user
        user = await get_or_create_user(session, allowed_user.telegram_id)
        tz = ZoneInfo(user.timezone or "Europe/Moscow")
        today = datetime.now(tz).date()

        tasks = await get_tasks_for_today(session, allowed_user.telegram_id, today)
        unfinished = [t for t in tasks if (t.status or 'grooming') in ('grooming', 'in_progress')]

        count = 0
        for task in unfinished:
            await update_task(session, task.id, allowed_user.telegram_id,
                              scheduled_date=target_date)
            count += 1

        await create_log(session, allowed_user.telegram_id, "tasks_rescheduled",
                         payload={"count": count, "target_date": target_date_str})
        await session.commit()

    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    day_label = f"{day_names[target_date.weekday()]}, {target_date.strftime('%d.%m')}"

    await callback.message.edit_text(
        f"🔄 *{count} задач* перенесено на {day_label}",
        parse_mode="Markdown",
    )
    await callback.answer(f"Перенесено {count} задач")


# === Завершить помодоро/блок ===


@router.callback_query(F.data.startswith("block_finish:"))
async def cb_block_finish(callback: CallbackQuery, allowed_user: AllowedUser):
    """Кнопка «✅ Завершить» — завершение помодоро-блока."""
    try:
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
    except Exception as e:
        logger.error(f"Ошибка в cb_block_finish: {e}", exc_info=True)
        await callback.answer(f"Ошибка: {e}", show_alert=True)


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
    try:
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
    except Exception as e:
        logger.error(f"Ошибка в cb_quest_done: {e}", exc_info=True)
        await callback.answer(f"Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("quest_partial:"))
async def cb_quest_partial(callback: CallbackQuery, allowed_user: AllowedUser):
    """Помодоро выполнен частично — спрашиваем причину."""
    try:
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
    except Exception as e:
        logger.error(f"Ошибка в cb_quest_partial: {e}", exc_info=True)
        await callback.answer(f"Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("quest_failed:"))
async def cb_quest_failed(callback: CallbackQuery, allowed_user: AllowedUser):
    """Помодоро не выполнен — спрашиваем причину."""
    try:
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
    except Exception as e:
        logger.error(f"Ошибка в cb_quest_failed: {e}", exc_info=True)
        await callback.answer(f"Ошибка: {e}", show_alert=True)


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
    try:
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
    except Exception as e:
        logger.error(f"Ошибка в cb_reason: {e}", exc_info=True)
        await callback.answer(f"Ошибка: {e}", show_alert=True)


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

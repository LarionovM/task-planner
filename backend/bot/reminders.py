"""Все типы напоминаний и спам-машина (v1.2.0 — помодоро-центричная).

Отвечает за:
- Помодоро-уведомления (старт, перерыв, резюме, опросник)
- Выбор задачи для помодоро
- Уведомления о событиях (созвоны, встречи)
- Итог дня + перенос невыполненных задач
- Экспоненциальный спам (помодоро + события)
- Восстановление после рестарта
"""

import asyncio
import logging
import random
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from backend.config import (
    SPAM_TEXTS,
    SPAM_TEXTS_EVENT,
    SPAM_QUESTIONNAIRE_TIMEOUT_SEC,
)
from backend.db.database import async_session
from backend.db.crud.blocks import (
    get_block,
    create_log,
    get_blocks_for_day,
    get_weekly_schedule,
)
from backend.db.crud.users import get_or_create_user, get_spam_config
from backend.db.crud.tasks import get_task, get_tasks_for_today, list_categories
from backend.db.crud.events import get_events_for_day
from backend.db.models import TaskBlock, Event

logger = logging.getLogger(__name__)

# === Хранилище спам-сообщений в памяти ===
# {user_id: list[message_id]} — для удаления при ответе
_spam_messages: dict[int, list[int]] = {}

# {user_id: asyncio.Task} — активные спам-таски (для опросника завершения)
_spam_tasks: dict[int, asyncio.Task] = {}

# {user_id: asyncio.Task} — спам-таски для игнора выбора задачи в помодоро
_pomo_pick_spam_tasks: dict[int, asyncio.Task] = {}

# {user_id} — пользователи, ожидающие нажатия кнопки выбора задачи
# Добавляется при отправке вопроса, удаляется при нажатии любой кнопки.
# _maybe_start_pomo_pick_spam проверяет наличие перед стартом спама.
_pomo_pick_pending: set[int] = set()

# Пользователи, которым уже отправлялось "нет задач" сегодня
# Сбрасывается при планировании нового дня (schedule_pomodoro_cycle)
_no_tasks_notified: set[int] = set()


# === Вспомогательные ===


def _is_in_working_hours(t: time, schedule_list, weekday: int | None = None) -> bool:
    """Проверяет, попадает ли текущее время в рабочие часы."""
    if weekday is None:
        weekday = datetime.now().weekday()
    for s in schedule_list:
        if s.day_of_week == weekday:
            if s.is_day_off:
                return False
            return s.active_from <= t <= s.active_to
    return True


async def _is_event_active(user_id: int) -> bool:
    """Проверяет, идёт ли сейчас активное событие у пользователя.

    Считаем активным только события СЕГОДНЯ, которые ещё не истекли
    больше чем на 1 час — чтобы забытые события прошлых дней не блокировали
    помодоро вечно.
    """
    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        tz = ZoneInfo(user.timezone or "Europe/Moscow")
        now = datetime.now(tz)
        today = now.date()

        from sqlalchemy import select
        result = await session.execute(
            select(Event).where(
                Event.user_id == user_id,
                Event.status == "active",
                Event.day == today,
            )
        )
        events = result.scalars().all()

    for event in events:
        end_time = event.end_time
        if isinstance(end_time, str):
            h, m = map(int, end_time.split(":"))
            end_time = time(h, m)
        end_dt = datetime.combine(today, end_time).replace(tzinfo=tz)
        # Считаем событие активным до 1 часа после его планового конца
        if now <= end_dt + timedelta(hours=1):
            return True
    return False


async def _is_event_upcoming(user_id: int, within_min: int = 25) -> Event | None:
    """Проверяет, есть ли запланированное событие в ближайшие within_min минут.

    Возвращает событие если есть, None если нет.
    """
    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        tz = ZoneInfo(user.timezone or "Europe/Moscow")
        now = datetime.now(tz)
        today = now.date()

        events = await get_events_for_day(session, user_id, today)
        for event in events:
            if event.status in ("done", "active"):
                continue
            event_start = event.start_time
            if isinstance(event_start, str):
                h, m = map(int, event_start.split(":"))
                event_start = time(h, m)
            event_dt = datetime.combine(today, event_start).replace(tzinfo=tz)
            diff_min = (event_dt - now).total_seconds() / 60
            if 0 <= diff_min <= within_min:
                return event
    return None


# === Помодоро-уведомления ===


async def send_pomodoro_start(user_id: int, pomodoro_number: int) -> None:
    """Уведомление о старте помодоро-сессии.

    Если есть задачи на сегодня — предлагает выбрать.
    Если нет — просто запускает помодоро без привязки к задаче.
    Если активно событие — не отправляет (тихий режим).
    """
    from backend.bot.scheduler import get_bot

    # Проверяем, не идёт ли событие
    if await _is_event_active(user_id):
        logger.debug(f"Помодоро #{pomodoro_number} для user={user_id} — пропуск, идёт событие")
        return

    # Проверяем, не на паузе/стопе ли напоминания
    async with async_session() as session:
        user = await get_or_create_user(session, user_id)

    if getattr(user, 'reminders_stopped', False):
        return

    paused_until = getattr(user, 'reminders_paused_until', None)
    if paused_until and paused_until > datetime.now():
        return

    # Определяем настройки помодоро пользователя
    work_min = user.pomodoro_work_min or 25
    cycles_before_long = user.pomodoro_cycles_before_long or 4

    # Проверяем, не начинается ли событие в ближайшие work_min минут
    upcoming_event = await _is_event_upcoming(user_id, within_min=work_min)
    if upcoming_event:
        event_name = upcoming_event.name
        logger.info(
            f"Помодоро #{pomodoro_number} для user={user_id} — пропуск, "
            f"событие «{event_name}» начинается в ближайшие {work_min} мин"
        )
        return

    bot = get_bot()

    # Получаем задачи на сегодня
    async with async_session() as session:
        tz = ZoneInfo(user.timezone or "Europe/Moscow")
        today = datetime.now(tz).date()
        tasks = await get_tasks_for_today(session, user_id, today)
        # Фильтруем: только grooming и in_progress (не done, не blocked)
        active_tasks = [t for t in tasks if (t.status or 'grooming') in ('grooming', 'in_progress')]

    if active_tasks:
        # Есть задачи — предлагаем выбрать
        rows = []
        for t in active_tasks[:8]:  # Максимум 8 кнопок
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.priority, "")
            label = t.name[:28] + "..." if len(t.name) > 28 else t.name
            rows.append([InlineKeyboardButton(
                text=f"{priority_emoji} {label}",
                callback_data=f"pomo:task:{t.id}:{pomodoro_number}",
            )])

        # Кнопка "Без задачи"
        rows.append([InlineKeyboardButton(
            text="🍅 Без задачи",
            callback_data=f"pomo:notask:{pomodoro_number}",
        )])
        # Кнопка "Пропустить"
        rows.append([InlineKeyboardButton(
            text="⏭ Пропустить",
            callback_data=f"pomo:skip:{pomodoro_number}",
        )])

        text = (
            f"⚡ *Фокус #{pomodoro_number}* — {work_min} мин\n"
            f"Какую задачу берёшь?"
        )

        msg = await bot.send_message(
            user_id, text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="Markdown",
        )

        # Запускаем спам если пользователь игнорирует выбор задачи
        _pomo_pick_pending.add(user_id)
        async with async_session() as session:
            spam_config = await get_spam_config(session, user_id)
        if spam_config and spam_config.enabled:
            loop = asyncio.get_event_loop()
            loop.call_later(
                SPAM_QUESTIONNAIRE_TIMEOUT_SEC,
                lambda uid=user_id, sc=spam_config: asyncio.ensure_future(
                    _maybe_start_pomo_pick_spam(uid, sc)
                ),
            )
    else:
        # Нет задач — после первого уведомления больше не спамим
        if user_id in _no_tasks_notified:
            logger.debug(
                f"Помодоро #{pomodoro_number} для user={user_id} — пропуск, "
                f"«нет задач» уже отправлялось"
            )
            return

        _no_tasks_notified.add(user_id)

        # Запускаем помодоро без привязки
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⏭ Пропустить",
                callback_data=f"pomo:skip:{pomodoro_number}",
            )],
        ])
        text = (
            f"⚡ *Фокус #{pomodoro_number}* — {work_min} мин\n"
            f"Задач на сегодня нет. Фокус начат! 🎯"
        )
        await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode="Markdown")

        # Создаём блок без задачи
        async with async_session() as session:
            tz = ZoneInfo(user.timezone or "Europe/Moscow")
            now = datetime.now(tz)
            block = TaskBlock(
                user_id=user_id,
                task_id=None,
                day=now.date(),
                start_time=now.time(),
                duration_min=work_min,
                status="active",
                pomodoro_number=pomodoro_number,
                actual_start_at=datetime.now(),
            )
            session.add(block)
            await create_log(session, user_id, "block_active",
                             payload={"pomodoro_number": pomodoro_number})
            await session.commit()

    async with async_session() as session:
        await create_log(session, user_id, "reminder_start",
                         payload={"pomodoro_number": pomodoro_number})
        await session.commit()


async def send_pomodoro_end_questionnaire(block_id: int) -> None:
    """Опросник по окончании помодоро: Выполнено / Частично / Не выполнено."""
    from backend.bot.scheduler import get_bot

    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(TaskBlock).where(TaskBlock.id == block_id))
        block = result.scalar_one_or_none()

    if not block or block.status not in ("active", "planned"):
        return

    bot = get_bot()

    # Получаем имя задачи
    task_name = "Задача"
    if block.task_id:
        async with async_session() as session:
            task = await get_task(session, block.task_id, block.user_id)
            if task:
                task_name = task.name

    text = f"🏁 *Фокус #{block.pomodoro_number or 1}* завершён!\n📝 {task_name}\n\nКак прошло?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выполнено", callback_data=f"quest_done:{block.id}"),
            InlineKeyboardButton(text="⚡ Частично", callback_data=f"quest_partial:{block.id}"),
        ],
        [
            InlineKeyboardButton(text="❌ Не выполнено", callback_data=f"quest_failed:{block.id}"),
        ],
    ])

    msg = await bot.send_message(block.user_id, text, reply_markup=keyboard, parse_mode="Markdown")

    # Через SPAM_QUESTIONNAIRE_TIMEOUT_SEC запустить спам если нет ответа
    loop = asyncio.get_event_loop()
    loop.call_later(
        SPAM_QUESTIONNAIRE_TIMEOUT_SEC,
        lambda: asyncio.ensure_future(_maybe_start_spam(block.user_id, block_id, msg.message_id)),
    )


async def send_pomodoro_break(user_id: int, pomodoro_number: int, is_long: bool = False) -> None:
    """Уведомление о перерыве (короткий или длинный)."""
    try:
        from backend.bot.scheduler import get_bot

        logger.debug(f"send_pomodoro_break: user={user_id}, pomo={pomodoro_number}, is_long={is_long}")

        # Проверяем, не идёт ли событие
        if await _is_event_active(user_id):
            logger.debug(f"Перерыв для user={user_id} пропущен — активное событие")
            return

        bot = get_bot()
        if not bot:
            logger.error(f"send_pomodoro_break: bot is None!")
            return

        async with async_session() as session:
            user = await get_or_create_user(session, user_id)

        if is_long:
            break_min = user.pomodoro_long_break_min or 30
            text = (
                f"🎉 *Длинный перерыв!* — {break_min} мин\n"
                f"Ты сделал {user.pomodoro_cycles_before_long or 4} цикла подряд! 💪\n"
                f"Отдохни как следует: прогуляйся, перекуси, разомнись 🧘"
            )
        else:
            break_min = user.pomodoro_short_break_min or 5
            text = (
                f"⏸ *Перерыв* — {break_min} мин\n"
                f"Встань, потянись, глотни воды 🌿"
            )

        await bot.send_message(user_id, text, parse_mode="Markdown")
        logger.info(f"Перерыв отправлен: user={user_id}, pomo={pomodoro_number}, long={is_long}")

        async with async_session() as session:
            event_type = "pomodoro_break"
            await create_log(session, user_id, event_type,
                             payload={"pomodoro_number": pomodoro_number, "is_long": is_long,
                                      "break_min": break_min})
            await session.commit()
    except Exception as e:
        logger.error(f"Ошибка в send_pomodoro_break: user={user_id}, pomo={pomodoro_number}: {e}", exc_info=True)


# === Уведомления о событиях ===


async def send_event_start(event_id: int) -> None:
    """Уведомление о начале события (созвон, встреча)."""
    from backend.bot.scheduler import get_bot

    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one_or_none()

        if not event or event.status == "done":
            return

        # Активируем событие
        event.status = "active"
        await create_log(session, event.user_id, "event_started",
                         payload={"event_id": event_id, "event_name": event.name})
        await session.commit()

        user = await get_or_create_user(session, event.user_id)
        categories = await list_categories(session, event.user_id)

    cat_map = {c.id: c for c in categories}
    cat = cat_map.get(event.category_id)
    cat_str = f" {cat.emoji}" if cat and cat.emoji else ""

    bot = get_bot()
    start_str = event.start_time.strftime("%H:%M") if event.start_time else "?"
    end_str = event.end_time.strftime("%H:%M") if event.end_time else "?"

    # Показываем описание и ссылку если есть у связанной задачи
    extra_lines = []
    if event.task_id:
        async with async_session() as session:
            task = await get_task(session, event.task_id, event.user_id)
            if task:
                if getattr(task, 'description', None):
                    extra_lines.append(f"📄 _{task.description}_")
                if getattr(task, 'link', None):
                    extra_lines.append(f"🔗 {task.link}")
    if event.notes:
        extra_lines.append(f"📝 {event.notes}")

    text = (
        f"📌 *Начинается:* {event.name}{cat_str}\n"
        f"⏱ {start_str} – {end_str}"
    )
    if extra_lines:
        text += "\n" + "\n".join(extra_lines)
    text += "\n\n_Уведомления о фокусе приостановлены на время события_"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Завершить событие",
            callback_data=f"event:finish:{event_id}",
        )],
    ])

    await bot.send_message(event.user_id, text, reply_markup=keyboard, parse_mode="Markdown")


async def send_event_end_reminder(event_id: int) -> None:
    """Напоминание: время события истекло, а оно не завершено — начинаем спам."""
    from backend.bot.scheduler import get_bot

    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one_or_none()

    if not event or event.status != "active":
        return

    bot = get_bot()
    text = (
        f"⏰ Время события *{event.name}* вышло!\n"
        f"Если оно завершилось — нажми кнопку."
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Завершить событие",
            callback_data=f"event:finish:{event_id}",
        )],
    ])

    msg = await bot.send_message(event.user_id, text, reply_markup=keyboard, parse_mode="Markdown")

    # Запускаем спам для события
    asyncio.get_event_loop().call_later(
        SPAM_QUESTIONNAIRE_TIMEOUT_SEC,
        lambda: asyncio.ensure_future(
            _maybe_start_event_spam(event.user_id, event_id, msg.message_id)
        ),
    )


async def send_event_prep_reminder(event_id: int) -> None:
    """Уведомление подготовки к событию (за N мин)."""
    from backend.bot.scheduler import get_bot

    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one_or_none()

        if not event or event.status in ("done", "active"):
            return

        user = await get_or_create_user(session, event.user_id)

    bot = get_bot()
    tz = ZoneInfo(user.timezone or "Europe/Moscow")
    now = datetime.now(tz)

    start_dt = datetime.combine(event.day, event.start_time).replace(tzinfo=tz)
    mins_left = max(1, int((start_dt - now).total_seconds() / 60))

    text = f"⏰ Через {mins_left} мин: *{event.name}*\nПодготовься! 🎯"

    await bot.send_message(event.user_id, text, parse_mode="Markdown")


# === Спам-машина ===


async def _maybe_start_spam(user_id: int, block_id: int, questionnaire_msg_id: int) -> None:
    """Проверяет нужно ли запускать спам для помодоро-опросника."""
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(TaskBlock).where(TaskBlock.id == block_id))
        block = result.scalar_one_or_none()

    if not block or block.status in ("done", "skipped", "failed", "partial"):
        return

    async with async_session() as session:
        # 1. spam_config.enabled
        spam_config = await get_spam_config(session, user_id)
        if not spam_config or not spam_config.enabled:
            return

        # 2. Категория в spam_category_ids (пусто = все)
        if block.task_id and spam_config.spam_category_ids:
            task = await get_task(session, block.task_id, user_id)
            if task and task.category_id not in spam_config.spam_category_ids:
                return

        # 3. task.spam_enabled
        if block.task_id:
            task = await get_task(session, block.task_id, user_id)
            if task and not task.spam_enabled:
                return

        # 4. Проверяем рабочее время
        user = await get_or_create_user(session, user_id)
        tz = ZoneInfo(user.timezone or "Europe/Moscow")
        now = datetime.now(tz)
        current_time = now.time()

        schedule = await get_weekly_schedule(session, user_id)
        if not _is_in_working_hours(current_time, schedule, now.weekday()):
            return

    # Запускаем спам
    await _start_spam_loop(user_id, block_id, spam_config, SPAM_TEXTS)


async def _maybe_start_pomo_pick_spam(user_id: int, spam_config) -> None:
    """Спам если пользователь проигнорировал выбор задачи в помодоро."""
    # Если пользователь уже нажал кнопку — маркер удалён, выходим
    if user_id not in _pomo_pick_pending:
        return
    _pomo_pick_pending.discard(user_id)

    from backend.bot.scheduler import get_bot
    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        tz = ZoneInfo(user.timezone or "Europe/Moscow")
        now = datetime.now(tz)
        schedule = await get_weekly_schedule(session, user_id)
        if not _is_in_working_hours(now.time(), schedule, now.weekday()):
            return

    bot = get_bot()
    interval = spam_config.initial_interval_sec
    texts = ["🍅 Ты выбрал задачу?", "Фокус ждёт! 👀", "Выбери задачу или нажми «Без задачи»",
             "tick tock... ⏰", "эй, не пропусти сессию фокуса 🍅"]
    text_idx = 0

    async def spam_loop():
        nonlocal interval, text_idx
        while True:
            await asyncio.sleep(interval)
            try:
                msg = await bot.send_message(user_id, texts[text_idx % len(texts)])
                _spam_messages.setdefault(user_id, []).append(msg.message_id)
            except Exception:
                break
            text_idx += 1
            interval = min(interval * spam_config.multiplier, spam_config.max_interval_sec)

    if user_id in _pomo_pick_spam_tasks:
        _pomo_pick_spam_tasks[user_id].cancel()
    task = asyncio.ensure_future(spam_loop())
    _pomo_pick_spam_tasks[user_id] = task


def stop_pomo_pick_spam(user_id: int) -> None:
    """Останавливает спам выбора задачи при нажатии любой кнопки помодоро."""
    _pomo_pick_pending.discard(user_id)  # маркер «ожидает нажатия» — сбрасываем
    if user_id in _pomo_pick_spam_tasks:
        _pomo_pick_spam_tasks[user_id].cancel()
        del _pomo_pick_spam_tasks[user_id]


async def _maybe_start_event_spam(user_id: int, event_id: int, msg_id: int) -> None:
    """Запускает спам для незавершённого события."""
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one_or_none()

    if not event or event.status != "active":
        return

    async with async_session() as session:
        spam_config = await get_spam_config(session, user_id)
        if not spam_config or not spam_config.enabled:
            return

    await _start_spam_loop(user_id, event_id, spam_config, SPAM_TEXTS_EVENT, is_event=True)


async def _start_spam_loop(
    user_id: int,
    target_id: int,
    spam_config,
    texts: list[str],
    is_event: bool = False,
) -> None:
    """Запускает экспоненциальный спам с расширенными текстами."""
    from backend.bot.scheduler import get_bot

    # Отменяем предыдущий спам если есть
    if user_id in _spam_tasks:
        _spam_tasks[user_id].cancel()

    bot = get_bot()
    _spam_messages.setdefault(user_id, [])

    async def spam_loop():
        interval = spam_config.initial_interval_sec
        text_index = 0
        shuffled_texts = texts.copy()
        random.shuffle(shuffled_texts)

        async with async_session() as session:
            await create_log(session, user_id, "spam_started",
                             payload={"target_id": target_id, "is_event": is_event})
            await session.commit()

        try:
            while True:
                await asyncio.sleep(interval)

                # Проверяем: блок/событие ещё активно?
                if is_event:
                    async with async_session() as session:
                        from sqlalchemy import select
                        result = await session.execute(
                            select(Event).where(Event.id == target_id)
                        )
                        obj = result.scalar_one_or_none()
                    if not obj or obj.status != "active":
                        break
                else:
                    async with async_session() as session:
                        from sqlalchemy import select
                        result = await session.execute(
                            select(TaskBlock).where(TaskBlock.id == target_id)
                        )
                        obj = result.scalar_one_or_none()
                    if not obj or obj.status in ("done", "skipped", "failed", "partial"):
                        break

                # Проверяем паузу / стоп / рабочее время
                async with async_session() as session:
                    user = await get_or_create_user(session, user_id)
                    tz = ZoneInfo(user.timezone or "Europe/Moscow")
                    now = datetime.now(tz)
                    current_time = now.time()

                    if getattr(user, 'reminders_stopped', False):
                        break
                    paused_until = getattr(user, 'reminders_paused_until', None)
                    if paused_until and paused_until > datetime.now():
                        break

                    schedule = await get_weekly_schedule(session, user_id)
                    if not _is_in_working_hours(current_time, schedule, now.weekday()):
                        break

                # Отправляем спам
                text = shuffled_texts[text_index % len(shuffled_texts)]
                try:
                    msg = await bot.send_message(user_id, text)
                    _spam_messages[user_id].append(msg.message_id)
                except Exception as e:
                    logger.error(f"Ошибка отправки спама user={user_id}: {e}")
                    break

                text_index += 1
                # Каждый круг текстов — пересортируем
                if text_index % len(shuffled_texts) == 0:
                    random.shuffle(shuffled_texts)

                interval = min(
                    interval * spam_config.multiplier,
                    spam_config.max_interval_sec,
                )

        except asyncio.CancelledError:
            pass
        finally:
            async with async_session() as session:
                await create_log(session, user_id, "spam_stopped",
                                 payload={"target_id": target_id, "is_event": is_event})
                await session.commit()

    task = asyncio.create_task(spam_loop())
    _spam_tasks[user_id] = task


async def stop_spam_and_cleanup(user_id: int) -> None:
    """Останавливает спам и удаляет все спам-сообщения."""
    from backend.bot.scheduler import get_bot

    # Останавливаем спам-таск
    if user_id in _spam_tasks:
        _spam_tasks[user_id].cancel()
        del _spam_tasks[user_id]

    # Удаляем спам-сообщения
    bot = get_bot()
    if user_id in _spam_messages:
        for msg_id in _spam_messages[user_id]:
            try:
                await bot.delete_message(user_id, msg_id)
            except Exception:
                pass  # Сообщение уже удалено или старое
        _spam_messages[user_id].clear()


# === Итог дня ===


async def send_day_summary(user_id: int) -> None:
    """Отправляет итог дня: помодоро-статистика + незавершённые задачи."""
    from backend.bot.scheduler import get_bot

    bot = get_bot()

    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        tz = ZoneInfo(user.timezone or "Europe/Moscow")
        today = datetime.now(tz).date()

        blocks = await get_blocks_for_day(session, user_id, today)
        tasks = await get_tasks_for_today(session, user_id, today)
        categories = await list_categories(session, user_id)

    cat_map = {c.id: c for c in categories}

    if not blocks and not tasks:
        return

    # Считаем помодоро-статистику
    done = sum(1 for b in blocks if b.status == "done")
    partial = sum(1 for b in blocks if b.status == "partial")
    failed = sum(1 for b in blocks if b.status == "failed")
    skipped = sum(1 for b in blocks if b.status == "skipped")
    total = len(blocks)

    # Время по категориям
    cat_time: dict[int, int] = {}
    async with async_session() as session:
        for block in blocks:
            if not block.task_id:
                continue
            task = await get_task(session, block.task_id, user_id)
            if not task:
                continue
            mins = block.actual_duration_min or block.duration_min or 25
            cat_time[task.category_id] = cat_time.get(task.category_id, 0) + mins

    # Незавершённые задачи
    unfinished = [t for t in tasks if (t.status or 'grooming') in ('grooming', 'in_progress')]

    lines = [
        f"📊 *Итог дня — {today.strftime('%d.%m.%Y')}*\n",
        f"🍅 Сессий фокуса: {total}",
        f"✅ Выполнено: {done}",
    ]
    if partial:
        lines.append(f"⚡ Частично: {partial}")
    if failed:
        lines.append(f"❌ Провалено: {failed}")
    if skipped:
        lines.append(f"⏭ Пропущено: {skipped}")

    # По категориям
    if cat_time:
        lines.append("\n📁 *По категориям:*")
        for cat_id, mins in cat_time.items():
            cat = cat_map.get(cat_id)
            if not cat:
                continue
            hours = mins // 60
            remainder = mins % 60
            time_str = f"{hours}ч {remainder}мин" if hours else f"{remainder}мин"
            lines.append(f"  {cat.emoji or ''} {cat.name}: {time_str}")

    text = "\n".join(lines)

    # Кнопки
    rows = []
    if unfinished:
        text += f"\n\n📋 *Незавершённых задач: {len(unfinished)}*"
        # Определяем следующий рабочий день
        async with async_session() as session:
            schedule = await get_weekly_schedule(session, user_id)

        next_day = today + timedelta(days=1)
        for _ in range(7):
            if _is_in_working_hours(time(12, 0), schedule, next_day.weekday()):
                break
            next_day += timedelta(days=1)

        day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        next_day_label = f"{day_names[next_day.weekday()]}, {next_day.strftime('%d.%m')}"

        rows.append([InlineKeyboardButton(
            text=f"🔄 Перенести на {next_day_label}",
            callback_data=f"eod:reschedule:{next_day.isoformat()}",
        )])

    from backend.config import settings
    if settings.frontend_url.startswith("https://"):
        from aiogram.types import WebAppInfo
        rows.append([InlineKeyboardButton(
            text="📅 Открыть планировщик",
            web_app=WebAppInfo(url=settings.frontend_url),
        )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

    await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode="Markdown")

    # Логируем
    async with async_session() as session:
        await create_log(session, user_id, "day_summary", payload={
            "done": done, "partial": partial, "failed": failed, "skipped": skipped,
            "total": total, "unfinished_count": len(unfinished),
        })
        await session.commit()


# === Восстановление при рестарте ===


async def send_restart_notification(user_id: int, block: TaskBlock) -> None:
    """Уведомление при рестарте.

    Если блок ещё не должен был завершиться — сообщаем что он в процессе,
    планируем опросник на реальное время окончания.
    Если время уже прошло — сразу задаём вопрос как прошёл.
    """
    from backend.bot.scheduler import get_bot

    bot = get_bot()

    task_name = "Задача"
    if block.task_id:
        async with async_session() as session:
            task = await get_task(session, block.task_id, user_id)
            if task:
                task_name = task.name

    # Определяем, прошло ли уже запланированное время окончания
    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        tz = ZoneInfo(user.timezone or "Europe/Moscow")

    now = datetime.now(tz)

    # Рассчитываем плановое время окончания блока
    if isinstance(block.start_time, str):
        h, m = map(int, block.start_time.split(":"))
        start_time_obj = time(h, m)
    else:
        start_time_obj = block.start_time

    block_start_dt = datetime.combine(block.day, start_time_obj).replace(tzinfo=tz)
    block_end_dt = block_start_dt + timedelta(minutes=block.duration_min or 25)

    if now < block_end_dt:
        # Блок ещё в процессе — сообщаем статус, не задаём вопрос
        remaining = int((block_end_dt - now).total_seconds() / 60)
        text = (
            f"🔄 Бот перезапустился.\n"
            f"«*{task_name}*» в процессе, осталось ~{remaining} мин."
        )
        await bot.send_message(user_id, text, parse_mode="Markdown")

        # Планируем опросник на конец блока
        from backend.bot.scheduler import _safe_add_job
        job_id = f"pomo_end_{user_id}_{block.id}"
        _safe_add_job(
            send_pomodoro_end_questionnaire,
            run_date=block_end_dt,
            args=[block.id],
            id=job_id,
        )
    else:
        # Время прошло — задаём опросник
        text = (
            f"🔄 Бот перезапустился.\n"
            f"«*{task_name}*» была активна — как прошло?"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнено", callback_data=f"quest_done:{block.id}"),
                InlineKeyboardButton(text="⚡ Частично", callback_data=f"quest_partial:{block.id}"),
            ],
            [
                InlineKeyboardButton(text="❌ Не выполнено", callback_data=f"quest_failed:{block.id}"),
            ],
        ])
        await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode="Markdown")

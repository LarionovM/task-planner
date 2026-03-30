"""APScheduler — помодоро-планировщик (v1.2.0).

Отвечает за:
- Автоматические помодоро-циклы (25+5, каждый 4-й — длинный перерыв)
- Планирование уведомлений о событиях (созвоны, встречи)
- Итог дня
- Восстановление при рестарте сервера
"""

import logging
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.db.database import async_session
from backend.db.crud.blocks import (
    get_planned_blocks_from_today,
    get_active_blocks,
    get_blocks_for_day,
    get_weekly_schedule,
)
from backend.db.crud.users import get_or_create_user, get_all_active_users
from backend.db.crud.events import get_events_for_day
from backend.db.models import TaskBlock, Event

logger = logging.getLogger(__name__)

# Глобальный scheduler
scheduler = AsyncIOScheduler()

# Ссылка на бота (устанавливается при инициализации)
_bot = None

# Счётчик помодоро за день {user_id: count}
_pomodoro_counts: dict[int, int] = {}


def init_scheduler(bot) -> AsyncIOScheduler:
    """Инициализирует scheduler и сохраняет ссылку на бота."""
    global _bot
    _bot = bot
    scheduler.start()
    logger.info("APScheduler запущен")
    return scheduler


def get_bot():
    """Возвращает экземпляр бота."""
    return _bot


def _make_job_id(prefix: str, obj_id: int, job_type: str) -> str:
    """Формирует уникальный ID для job-а."""
    return f"{prefix}_{obj_id}_{job_type}"


def _user_now(tz_name: str) -> datetime:
    """Текущее время пользователя."""
    tz = ZoneInfo(tz_name)
    return datetime.now(tz)


def _combine_user_dt(day: date, t: time, tz_name: str) -> datetime:
    """Собирает datetime из даты + времени + timezone пользователя."""
    tz = ZoneInfo(tz_name)
    naive = datetime.combine(day, t)
    return naive.replace(tzinfo=tz)


def _safe_add_job(func, run_date, args, id, **kwargs):
    """Добавляет job, удаляя старый с тем же ID если есть."""
    existing = scheduler.get_job(id)
    if existing:
        scheduler.remove_job(id)
    scheduler.add_job(
        func,
        trigger="date",
        run_date=run_date,
        args=args,
        id=id,
        misfire_grace_time=300,  # 5 мин grace period
        **kwargs,
    )


def cancel_block_jobs(block_id: int) -> None:
    """Отменяет все jobs для блока."""
    for suffix in ["start", "end", "break", "resume"]:
        job_id = _make_job_id("pomo", block_id, suffix)
        job = scheduler.get_job(job_id)
        if job:
            scheduler.remove_job(job_id)
            logger.debug(f"Job {job_id} отменён")


def cancel_event_jobs(event_id: int) -> None:
    """Отменяет все jobs для события."""
    for suffix in ["prep", "start", "end"]:
        job_id = _make_job_id("event", event_id, suffix)
        job = scheduler.get_job(job_id)
        if job:
            scheduler.remove_job(job_id)
            logger.debug(f"Job {job_id} отменён")


# === Помодоро-циклы ===


async def schedule_pomodoro_cycle(user_id: int, user_tz: str = "Europe/Moscow") -> None:
    """Планирует весь день помодоро-циклов для пользователя.

    Циклы: 25 мин работа → 5 мин перерыв → 25 мин → 5 мин → ... → 25 мин → 30 мин (длинный перерыв).
    Помодоро не отправляется во время активных событий (проверяется в reminders.py).
    """
    from backend.bot.reminders import send_pomodoro_start, send_pomodoro_break, send_pomodoro_end_questionnaire

    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        schedule = await get_weekly_schedule(session, user_id)

    tz = ZoneInfo(user_tz)
    now = datetime.now(tz)
    today = now.date()
    weekday = today.weekday()

    # Проверяем: сегодня не выходной?
    day_sched = next((s for s in schedule if s.day_of_week == weekday), None)
    if not day_sched or day_sched.is_day_off:
        logger.debug(f"Помодоро для user={user_id}: сегодня выходной")
        return

    # Настройки помодоро
    work_min = user.pomodoro_work_min or 25
    short_break = user.pomodoro_short_break_min or 5
    long_break = user.pomodoro_long_break_min or 30
    cycles_before_long = user.pomodoro_cycles_before_long or 4

    # Рабочие часы
    active_from = day_sched.active_from
    active_to = day_sched.active_to
    if isinstance(active_from, str):
        h, m = map(int, active_from.split(":"))
        active_from = time(h, m)
    if isinstance(active_to, str):
        h, m = map(int, active_to.split(":"))
        active_to = time(h, m)

    # Стартуем от active_from (или от текущего времени, если уже позже)
    start_dt = _combine_user_dt(today, active_from, user_tz)
    end_dt = _combine_user_dt(today, active_to, user_tz)

    if now > end_dt:
        logger.debug(f"Помодоро для user={user_id}: рабочий день закончился")
        return

    # Если сейчас позже начала — начинаем с ближайшего полного цикла
    if now > start_dt:
        # Округляем до ближайшего будущего слота
        elapsed = (now - start_dt).total_seconds() / 60
        cycle_len = work_min + short_break
        next_cycle = int(elapsed / cycle_len) + 1
        start_dt = start_dt + timedelta(minutes=next_cycle * cycle_len - short_break)
        # Номер помодоро
        start_pomo_number = next_cycle + 1
    else:
        start_pomo_number = 1

    # Планируем помодоро-циклы
    current_dt = start_dt if start_dt > now else now + timedelta(minutes=1)
    pomo_number = start_pomo_number

    while current_dt < end_dt:
        # Помодоро-старт
        if current_dt > now:
            job_id = f"pomo_start_{user_id}_{pomo_number}"
            _safe_add_job(
                send_pomodoro_start,
                run_date=current_dt,
                args=[user_id, pomo_number],
                id=job_id,
            )

        # Конец помодоро (опросник) через work_min
        end_pomo_dt = current_dt + timedelta(minutes=work_min)
        if end_pomo_dt > now and end_pomo_dt < end_dt:
            # Опросник будет вызываться из callback при создании блока
            # Но для блоков без задачи нужен scheduled end
            pass

        # Перерыв
        is_long_break = (pomo_number % cycles_before_long == 0)
        break_min = long_break if is_long_break else short_break

        break_dt = current_dt + timedelta(minutes=work_min)
        if break_dt > now and break_dt < end_dt:
            job_id = f"pomo_break_{user_id}_{pomo_number}"
            _safe_add_job(
                send_pomodoro_break,
                run_date=break_dt,
                args=[user_id, pomo_number, is_long_break],
                id=job_id,
            )

        # Следующий помодоро после перерыва
        current_dt = break_dt + timedelta(minutes=break_min)
        pomo_number += 1

    _pomodoro_counts[user_id] = pomo_number - 1
    logger.info(f"Помодоро для user={user_id}: запланировано {pomo_number - start_pomo_number} циклов")


# === Планирование событий ===


async def schedule_event_jobs(event: Event, user_tz: str = "Europe/Moscow") -> None:
    """Планирует jobs для одного события (prep, start, end)."""
    from backend.bot.reminders import send_event_prep_reminder, send_event_start, send_event_end_reminder

    now = _user_now(user_tz)

    if isinstance(event.start_time, str):
        h, m = map(int, event.start_time.split(":"))
        start_time = time(h, m)
    else:
        start_time = event.start_time

    if isinstance(event.end_time, str):
        h, m = map(int, event.end_time.split(":"))
        end_time = time(h, m)
    else:
        end_time = event.end_time

    event_start_dt = _combine_user_dt(event.day, start_time, user_tz)
    event_end_dt = _combine_user_dt(event.day, end_time, user_tz)

    # Подготовка (за reminder_before_min)
    reminder_before = event.reminder_before_min or 5
    prep_dt = event_start_dt - timedelta(minutes=reminder_before)
    if prep_dt > now:
        job_id = _make_job_id("event", event.id, "prep")
        _safe_add_job(
            send_event_prep_reminder,
            run_date=prep_dt,
            args=[event.id],
            id=job_id,
        )

    # Старт события
    if event_start_dt > now:
        job_id = _make_job_id("event", event.id, "start")
        _safe_add_job(
            send_event_start,
            run_date=event_start_dt,
            args=[event.id],
            id=job_id,
        )

    # Конец события (напоминание о завершении)
    if event_end_dt > now:
        job_id = _make_job_id("event", event.id, "end")
        _safe_add_job(
            send_event_end_reminder,
            run_date=event_end_dt,
            args=[event.id],
            id=job_id,
        )

    logger.info(f"Jobs для события #{event.id} «{event.name}» запланированы")


# === Итог дня ===


async def schedule_day_summary(user_id: int, user_tz: str) -> None:
    """Планирует итог дня для пользователя."""
    from backend.bot.reminders import send_day_summary

    async with async_session() as session:
        user = await get_or_create_user(session, user_id)

    tz = ZoneInfo(user_tz)
    now = datetime.now(tz)
    today = now.date()

    # Время итога дня
    end_time = user.day_end_time or time(23, 50)
    summary_dt = datetime.combine(today, end_time).replace(tzinfo=tz)

    # Если время уже прошло — на завтра
    if summary_dt <= now:
        summary_dt += timedelta(days=1)

    job_id = f"day_summary_{user_id}"
    _safe_add_job(
        send_day_summary,
        run_date=summary_dt,
        args=[user_id],
        id=job_id,
    )
    logger.debug(f"Итог дня для user={user_id} запланирован на {summary_dt}")


# === Восстановление при рестарте ===


async def restore_jobs_on_startup() -> None:
    """Восстанавливает все jobs при рестарте сервера.

    1. Помодоро-циклы для всех активных пользователей
    2. События на сегодня
    3. Активные блоки без завершения → уведомить
    4. Итог дня для всех
    """
    from backend.bot.reminders import send_restart_notification

    logger.info("Восстановление jobs при рестарте...")

    async with async_session() as session:
        all_users = await get_all_active_users(session)

    for user in all_users:
        user_tz = user.timezone or "Europe/Moscow"
        tz = ZoneInfo(user_tz)
        today = datetime.now(tz).date()

        # 1. Помодоро-циклы на сегодня
        await schedule_pomodoro_cycle(user.telegram_id, user_tz)

        # 2. События на сегодня
        async with async_session() as session:
            events = await get_events_for_day(session, user.telegram_id, today)
            for event in events:
                if event.status not in ("done",):
                    await schedule_event_jobs(event, user_tz)

        # 3. Активные блоки (сервер упал во время помодоро)
        async with async_session() as session:
            active_blocks = await get_active_blocks(session)
            for block in active_blocks:
                if block.user_id == user.telegram_id:
                    await send_restart_notification(user.telegram_id, block)

        # 4. Итог дня
        await schedule_day_summary(user.telegram_id, user_tz)

    jobs_count = len(scheduler.get_jobs())
    logger.info(f"Восстановление завершено. Всего jobs: {jobs_count}")

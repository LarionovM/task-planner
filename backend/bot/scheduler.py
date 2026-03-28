"""APScheduler — планировщик напоминаний.

Отвечает за:
- Инициализацию AsyncIOScheduler
- Планирование jobs для блоков (prep, start, end, pomodoro, max_duration)
- Восстановление jobs при рестарте сервера
- Планирование итога дня
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
)
from backend.db.crud.users import get_or_create_user, get_all_active_users
from backend.db.models import TaskBlock

logger = logging.getLogger(__name__)

# Глобальный scheduler
scheduler = AsyncIOScheduler()

# Ссылка на бота (устанавливается при инициализации)
_bot = None


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


def _make_job_id(block_id: int, job_type: str) -> str:
    """Формирует уникальный ID для job-а."""
    return f"block_{block_id}_{job_type}"


def _user_now(tz_name: str) -> datetime:
    """Текущее время пользователя."""
    tz = ZoneInfo(tz_name)
    return datetime.now(tz)


def _combine_user_dt(day: date, t: time, tz_name: str) -> datetime:
    """Собирает datetime из даты + времени + timezone пользователя."""
    tz = ZoneInfo(tz_name)
    naive = datetime.combine(day, t)
    return naive.replace(tzinfo=tz)


async def schedule_block_jobs(block: TaskBlock, user_tz: str = "Europe/Moscow") -> None:
    """Планирует все jobs для одного блока.

    Jobs:
    - reminder_prep: за reminder_before_min до старта
    - reminder_start: в момент старта
    - block_end: в момент окончания (для fixed)
    - min_duration_reached: через min_duration (для range)
    - max_duration_reminder: через max_duration (для open/range)
    - pomodoro_*: циклы 25+5 мин (если use_pomodoro)
    """
    from backend.bot.reminders import (
        send_prep_reminder,
        send_start_reminder,
        send_block_end_questionnaire,
        send_min_duration_reached,
        send_max_duration_reminder,
        schedule_pomodoro_jobs,
    )

    now = _user_now(user_tz)
    block_start_dt = _combine_user_dt(block.day, block.start_time, user_tz)

    # Получаем reminder_before_min из первой задачи блока
    reminder_before = 5  # default
    if block.task_ids:
        async with async_session() as session:
            from backend.db.crud.tasks import get_task
            task = await get_task(session, block.task_ids[0], block.user_id)
            if task:
                reminder_before = task.reminder_before_min or 5

    # === 1. Подготовка (за N мин до старта) ===
    prep_dt = block_start_dt - timedelta(minutes=reminder_before)
    if prep_dt > now:
        job_id = _make_job_id(block.id, "prep")
        _safe_add_job(
            send_prep_reminder,
            run_date=prep_dt,
            args=[block.id],
            id=job_id,
        )
        logger.debug(f"Job {job_id} запланирован на {prep_dt}")

    # === 2. Старт блока ===
    if block_start_dt > now:
        job_id = _make_job_id(block.id, "start")
        _safe_add_job(
            send_start_reminder,
            run_date=block_start_dt,
            args=[block.id],
            id=job_id,
        )
        logger.debug(f"Job {job_id} запланирован на {block_start_dt}")

    # === 3. Окончание / напоминания по типу блока ===
    if block.duration_type == "fixed":
        # Фиксированный блок: опросник по окончании
        duration = block.duration_min or 60
        end_dt = block_start_dt + timedelta(minutes=duration)
        if end_dt > now:
            job_id = _make_job_id(block.id, "end")
            _safe_add_job(
                send_block_end_questionnaire,
                run_date=end_dt,
                args=[block.id],
                id=job_id,
            )

        # Pomodoro jobs если включён
        if block.task_ids:
            async with async_session() as session:
                from backend.db.crud.tasks import get_task
                task = await get_task(session, block.task_ids[0], block.user_id)
                if task and task.use_pomodoro and duration >= 30:
                    await schedule_pomodoro_jobs(block, user_tz, now)

    elif block.duration_type == "range":
        # Диапазон: напоминание о min_duration, потом max_duration
        if block.min_duration_min:
            min_dt = block_start_dt + timedelta(minutes=block.min_duration_min)
            if min_dt > now:
                job_id = _make_job_id(block.id, "min_reached")
                _safe_add_job(
                    send_min_duration_reached,
                    run_date=min_dt,
                    args=[block.id],
                    id=job_id,
                )
        if block.max_duration_min:
            max_dt = block_start_dt + timedelta(minutes=block.max_duration_min)
            if max_dt > now:
                job_id = _make_job_id(block.id, "max_reminder")
                _safe_add_job(
                    send_max_duration_reminder,
                    run_date=max_dt,
                    args=[block.id],
                    id=job_id,
                )

    elif block.duration_type == "open":
        # Открытый блок: напоминание через max_duration (если задан)
        if block.max_duration_min:
            max_dt = block_start_dt + timedelta(minutes=block.max_duration_min)
            if max_dt > now:
                job_id = _make_job_id(block.id, "max_reminder")
                _safe_add_job(
                    send_max_duration_reminder,
                    run_date=max_dt,
                    args=[block.id],
                    id=job_id,
                )

    logger.info(f"Jobs запланированы для блока #{block.id} ({block.block_name})")


def cancel_block_jobs(block_id: int) -> None:
    """Отменяет все jobs для блока."""
    prefixes = ["prep", "start", "end", "min_reached", "max_reminder"]
    # Также отменяем pomodoro jobs
    for i in range(20):  # максимум 20 pomodoro-циклов
        prefixes.append(f"pomo_break_{i}")
        prefixes.append(f"pomo_resume_{i}")

    for suffix in prefixes:
        job_id = _make_job_id(block_id, suffix)
        job = scheduler.get_job(job_id)
        if job:
            scheduler.remove_job(job_id)
            logger.debug(f"Job {job_id} отменён")


def _safe_add_job(func, run_date, args, id):
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
    )


async def restore_jobs_on_startup() -> None:
    """Восстанавливает все jobs при рестарте сервера.

    1. Planned блоки → планирует prep/start/end jobs
    2. Active блоки без actual_end_at → уведомляет пользователя
    3. Итог дня для всех пользователей
    """
    from backend.bot.reminders import send_restart_active_block_notification

    logger.info("Восстановление jobs при рестарте...")

    async with async_session() as session:
        # 1. Planned блоки → запланировать jobs
        planned_blocks = await get_planned_blocks_from_today(session)
        logger.info(f"Найдено {len(planned_blocks)} planned блоков")

        for block in planned_blocks:
            user = await get_or_create_user(session, block.user_id)
            user_tz = user.timezone or "Europe/Moscow"
            await schedule_block_jobs(block, user_tz)

        # 2. Active блоки (сервер упал во время выполнения)
        active_blocks = await get_active_blocks(session)
        logger.info(f"Найдено {len(active_blocks)} активных блоков при рестарте")

        for block in active_blocks:
            user = await get_or_create_user(session, block.user_id)
            user_tz = user.timezone or "Europe/Moscow"
            now = _user_now(user_tz)

            # Определяем когда блок должен закончиться
            block_start_dt = _combine_user_dt(block.day, block.start_time, user_tz)
            if block.duration_type == "fixed":
                block_end_dt = block_start_dt + timedelta(minutes=block.duration_min or 60)
            elif block.duration_type == "range":
                block_end_dt = block_start_dt + timedelta(minutes=block.max_duration_min or 60)
            else:
                # open — заканчивается по max_duration или через 8 часов (fallback)
                block_end_dt = block_start_dt + timedelta(minutes=block.max_duration_min or 480)

            # Блок ещё идёт — запланировать end questionnaire вместо спрашивания
            if block_end_dt > now:
                from backend.bot.reminders import send_block_end_questionnaire
                job_id = _make_job_id(block.id, "end")
                _safe_add_job(
                    send_block_end_questionnaire,
                    run_date=block_end_dt,
                    args=[block.id],
                    id=job_id,
                )
                logger.info(f"Блок #{block.id} ещё идёт — запланирован end questionnaire на {block_end_dt}")

                # Для range: запланировать min_duration_reached если ещё не прошло
                if block.duration_type == "range" and block.min_duration_min:
                    min_dt = block_start_dt + timedelta(minutes=block.min_duration_min)
                    if min_dt > now:
                        from backend.bot.reminders import send_min_duration_reached
                        min_job_id = _make_job_id(block.id, "min_dur")
                        _safe_add_job(
                            send_min_duration_reached,
                            run_date=min_dt,
                            args=[block.id],
                            id=min_job_id,
                        )

                # Для open/range: запланировать max_duration_reminder
                if block.actual_start_at and block.max_duration_min:
                    max_dt = block.actual_start_at + timedelta(minutes=block.max_duration_min)
                    max_dt_aware = max_dt.replace(tzinfo=ZoneInfo(user_tz)) if max_dt.tzinfo is None else max_dt
                    if max_dt_aware > now:
                        from backend.bot.reminders import send_max_duration_reminder
                        max_job_id = _make_job_id(block.id, "max_reminder")
                        _safe_add_job(
                            send_max_duration_reminder,
                            run_date=max_dt_aware,
                            args=[block.id],
                            id=max_job_id,
                        )

                # Pomodoro jobs если нужно
                if block.duration_type == "fixed" and block.task_ids:
                    from backend.db.crud.tasks import get_task
                    task = await get_task(session, block.task_ids[0], block.user_id)
                    if task and task.use_pomodoro:
                        from backend.bot.reminders import schedule_pomodoro_jobs
                        await schedule_pomodoro_jobs(block, user_tz, now)

                continue

            # Блок уже должен был закончиться — спросить пользователя
            # Но сначала проверим max_duration для open/range
            if block.actual_start_at and block.max_duration_min:
                max_dt = block.actual_start_at + timedelta(minutes=block.max_duration_min)
                max_dt_aware = max_dt.replace(tzinfo=ZoneInfo(user_tz)) if max_dt.tzinfo is None else max_dt
                if max_dt_aware > now:
                    from backend.bot.reminders import send_max_duration_reminder
                    job_id = _make_job_id(block.id, "max_reminder")
                    _safe_add_job(
                        send_max_duration_reminder,
                        run_date=max_dt_aware,
                        args=[block.id],
                        id=job_id,
                    )
                    continue

            # Блок просрочен — спросить как прошёл
            await send_restart_active_block_notification(block)

        # 3. Итог дня и проверка пустых слотов для всех пользователей
        all_users = await get_all_active_users(session)
        for user in all_users:
            user_tz = user.timezone or "Europe/Moscow"
            await schedule_day_summary(user.telegram_id, user_tz)
            await schedule_empty_slots_check(user.telegram_id, user_tz)

    jobs_count = len(scheduler.get_jobs())
    logger.info(f"Восстановление завершено. Всего jobs: {jobs_count}")


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

    # Проверяем тихое время: если итог попадает в тихое — перенести на quiet_end
    quiet_start = user.quiet_start or time(23, 0)
    quiet_end = user.quiet_end or time(8, 0)

    summary_time = summary_dt.time()
    in_quiet = _is_in_quiet_time(summary_time, quiet_start, quiet_end)

    if in_quiet:
        # Переносим на quiet_end следующего утра
        next_day = summary_dt.date() + timedelta(days=1)
        summary_dt = datetime.combine(next_day, quiet_end).replace(tzinfo=tz)

    job_id = f"day_summary_{user_id}"
    _safe_add_job(
        send_day_summary,
        run_date=summary_dt,
        args=[user_id],
        id=job_id,
    )
    logger.debug(f"Итог дня для user={user_id} запланирован на {summary_dt}")


async def schedule_empty_slots_check(user_id: int, user_tz: str) -> None:
    """Планирует проверку пустых слотов: вечером (за час до day_end_time) и утром (active_from)."""
    from backend.bot.reminders import (
        send_empty_slots_evening_reminder,
        send_empty_slots_morning_reminder,
    )

    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        from backend.db.crud.users import get_spam_config
        spam_config = await get_spam_config(session, user_id)
        if not spam_config or not spam_config.empty_slots_enabled:
            return

        from backend.db.crud.blocks import get_weekly_schedule
        schedule = await get_weekly_schedule(session, user_id)

    tz = ZoneInfo(user_tz)
    now = datetime.now(tz)
    today = now.date()

    # === Вечернее напоминание ===
    # За 1 час до day_end_time
    day_end = user.day_end_time or time(23, 50)
    evening_time = (datetime.combine(today, day_end) - timedelta(hours=1)).time()
    evening_dt = datetime.combine(today, evening_time).replace(tzinfo=tz)

    # Если время уже прошло — на завтра
    if evening_dt <= now:
        evening_dt += timedelta(days=1)

    # Проверяем: не в тихое время
    quiet_start = user.quiet_start or time(23, 0)
    quiet_end = user.quiet_end or time(8, 0)
    if not _is_in_quiet_time(evening_dt.time(), quiet_start, quiet_end):
        job_id = f"empty_slots_evening_{user_id}"
        _safe_add_job(
            send_empty_slots_evening_reminder,
            run_date=evening_dt,
            args=[user_id],
            id=job_id,
        )
        logger.debug(f"Проверка пустых слотов (вечер) для user={user_id} на {evening_dt}")

    # === Утреннее напоминание ===
    # В active_from рабочего дня (завтра)
    tomorrow = today + timedelta(days=1)
    tomorrow_weekday = tomorrow.weekday()
    day_sched = next((s for s in schedule if s.day_of_week == tomorrow_weekday), None)

    if day_sched and not day_sched.is_day_off:
        morning_dt = datetime.combine(tomorrow, day_sched.active_from).replace(tzinfo=tz)
        # Если завтра уже прошло (маловероятно, но на всякий случай)
        if morning_dt > now:
            job_id = f"empty_slots_morning_{user_id}"
            _safe_add_job(
                send_empty_slots_morning_reminder,
                run_date=morning_dt,
                args=[user_id],
                id=job_id,
            )
            logger.debug(f"Проверка пустых слотов (утро) для user={user_id} на {morning_dt}")


def _is_in_quiet_time(t: time, quiet_start: time, quiet_end: time) -> bool:
    """Проверяет, попадает ли время в тихое время.

    Поддерживает перенос через полночь (23:00 → 08:00).
    """
    if quiet_start <= quiet_end:
        # Тихое время внутри дня (напр. 01:00-06:00)
        return quiet_start <= t <= quiet_end
    else:
        # Тихое время через полночь (напр. 23:00-08:00)
        return t >= quiet_start or t <= quiet_end

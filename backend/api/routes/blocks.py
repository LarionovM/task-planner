"""API маршруты для блоков календаря."""

from datetime import date, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.api.schemas import (
    BlockCreate,
    BlockUpdate,
    BlockResponse,
    BlockCreateResponse,
    BlockUpdateResponse,
    BlockWarning,
)
from backend.db.database import get_db
from backend.db.crud.blocks import (
    list_blocks_for_week,
    get_block,
    create_block,
    update_block,
    delete_block,
    get_blocks_for_day,
)
from sqlalchemy import select
from backend.db.crud.tasks import list_tasks, get_task
from backend.db.models import AllowedUser, TaskBlock

router = APIRouter(prefix="/api/blocks", tags=["blocks"])

# Веса приоритетов для мульти-распределения
PRIORITY_WEIGHTS = {"high": 3, "medium": 2, "low": 1}


def _calculate_multi_distribution(
    group_tasks: list,
    block_duration_min: int,
) -> list[int]:
    """Рассчитать распределение задач в блоке с дубликатами.

    Для одной задачи: task × N где N = block_duration / task_duration.
    Для группы задач: взвешенное распределение по приоритету.
    Только для задач с allow_multi_per_block=True.
    """
    import random

    # Фильтр: мульти-задачи и обычные
    multi_tasks = [t for t in group_tasks if t.allow_multi_per_block]
    single_tasks = [t for t in group_tasks if not t.allow_multi_per_block]

    # Начинаем с одиночных задач (по 1 разу каждая)
    result_ids: list[int] = [t.id for t in single_tasks]
    used_time = sum(t.estimated_time_min or 5 for t in single_tasks)
    remaining = block_duration_min - used_time

    if remaining <= 0 or not multi_tasks:
        # Если мульти-задач нет, просто по одному разу
        result_ids.extend(t.id for t in multi_tasks)
        return result_ids

    # Одна мульти-задача → простое деление
    if len(multi_tasks) == 1:
        task = multi_tasks[0]
        dur = task.estimated_time_min or 5
        count = max(1, remaining // dur)
        result_ids.extend([task.id] * count)
        return result_ids

    # Несколько мульти-задач → взвешенное распределение
    total_weight = sum(PRIORITY_WEIGHTS.get(t.priority, 2) for t in multi_tasks)
    for task in multi_tasks:
        weight = PRIORITY_WEIGHTS.get(task.priority, 2)
        dur = task.estimated_time_min or 5
        # Пропорция: weight / total_weight * remaining / dur
        share = (weight / total_weight) * remaining
        count = max(1, round(share / dur))
        result_ids.extend([task.id] * count)

    random.shuffle(result_ids)
    return result_ids


def _is_preferred_time_match(preferred: "time | None", slot_time: "time", tolerance_min: int = 30) -> bool:
    """Проверить, попадает ли слот в preferred_time ± tolerance."""
    if preferred is None:
        return True  # Без preferred_time — любой слот подходит
    pref_min = preferred.hour * 60 + preferred.minute
    slot_min = slot_time.hour * 60 + slot_time.minute
    return abs(pref_min - slot_min) <= tolerance_min


def _preferred_time_bucket(preferred: "time | None") -> str:
    """Вычислить временной бакет для группировки задач по preferred_time.

    Задачи в пределах ±30 мин должны попадать в один бакет.
    Используем floor до часа: 11:00 и 11:30 оба → бакет "11".
    Задачи без preferred_time получают бакет "any" (совместимы с любыми).
    """
    if preferred is None:
        return "any"
    return str(preferred.hour)


def _split_group_by_preferred_time(tasks_list: list, tolerance_min: int = 30) -> list[list]:
    """Разбить группу задач на подгруппы по совместимости preferred_time.

    Задачи без preferred_time присоединяются к первой подгруппе.
    Задачи с preferred_time в пределах ±tolerance_min объединяются.
    """
    if len(tasks_list) <= 1:
        return [tasks_list]

    # Разделяем: с preferred_time и без
    with_pref = [t for t in tasks_list if t.preferred_time is not None]
    without_pref = [t for t in tasks_list if t.preferred_time is None]

    if not with_pref:
        return [tasks_list]

    # Сортируем по preferred_time
    with_pref.sort(key=lambda t: t.preferred_time.hour * 60 + t.preferred_time.minute)

    # Жадная группировка: каждая новая задача присоединяется к последней подгруппе
    # если её preferred_time совместим со ВСЕМИ задачами в подгруппе
    subgroups: list[list] = [[with_pref[0]]]
    for task in with_pref[1:]:
        # Проверяем совместимость с якорем подгруппы (первой задачей)
        anchor = subgroups[-1][0]
        if _are_preferred_times_compatible(anchor.preferred_time, task.preferred_time, tolerance_min):
            subgroups[-1].append(task)
        else:
            subgroups.append([task])

    # Задачи без preferred_time добавляем в первую подгруппу
    subgroups[0].extend(without_pref)

    return subgroups


def _are_preferred_times_compatible(t1: "time | None", t2: "time | None", tolerance_min: int = 30) -> bool:
    """Проверить, совместимы ли два preferred_time для группировки (±tolerance)."""
    if t1 is None or t2 is None:
        return True  # Без preferred_time — совместим с любым
    t1_min = t1.hour * 60 + t1.minute
    t2_min = t2.hour * 60 + t2.minute
    return abs(t1_min - t2_min) <= tolerance_min


def _earliest_preferred_time(tasks_list: list) -> "time | None":
    """Вернуть самое раннее preferred_time из списка задач (или None)."""
    prefs = [t.preferred_time for t in tasks_list if t.preferred_time is not None]
    if not prefs:
        return None
    return min(prefs, key=lambda t: t.hour * 60 + t.minute)


def _str_to_time(s: str) -> time:
    """HH:MM → time."""
    parts = s.split(":")
    return time(int(parts[0]), int(parts[1]))


def _time_to_str(t: time) -> str:
    """time → HH:MM."""
    return t.strftime("%H:%M")


def _block_to_response(block) -> BlockResponse:
    """Конвертирует модель блока в ответ API."""
    return BlockResponse(
        id=block.id,
        task_ids=block.task_ids or [],
        block_name=block.block_name,
        day=block.day,
        start_time=_time_to_str(block.start_time),
        duration_type=block.duration_type,
        duration_min=block.duration_min,
        min_duration_min=block.min_duration_min,
        max_duration_min=block.max_duration_min,
        actual_start_at=block.actual_start_at,
        actual_end_at=block.actual_end_at,
        actual_duration_min=block.actual_duration_min,
        status=block.status,
        is_mixed=block.is_mixed,
        notes=block.notes,
        created_at=block.created_at,
    )


@router.get("", response_model=list[BlockResponse])
async def get_blocks(
    week_start: date = Query(..., description="Начало недели (YYYY-MM-DD)"),
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Блоки на неделю."""
    blocks = await list_blocks_for_week(session, allowed.telegram_id, week_start)
    return [_block_to_response(b) for b in blocks]


@router.get("/{block_id}", response_model=BlockResponse)
async def get_block_by_id(
    block_id: int,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Получить блок по ID."""
    block = await get_block(session, block_id, allowed.telegram_id)
    if block is None:
        raise HTTPException(status_code=404, detail="Блок не найден")
    return _block_to_response(block)


@router.post("", response_model=BlockCreateResponse, status_code=201)
async def post_block(
    data: BlockCreate,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Создать блок. Возвращает предупреждения о пересечениях."""
    # Валидация duration_type
    if data.duration_type not in ("fixed", "open", "range"):
        raise HTTPException(status_code=400, detail="duration_type должен быть fixed, open или range")

    if data.duration_type == "fixed" and not data.duration_min:
        raise HTTPException(status_code=400, detail="Для fixed блока нужен duration_min")

    if data.duration_type == "range":
        if not data.min_duration_min or not data.max_duration_min:
            raise HTTPException(status_code=400, detail="Для range блока нужны min_duration_min и max_duration_min")
        if data.min_duration_min >= data.max_duration_min:
            raise HTTPException(status_code=400, detail="min_duration_min должен быть меньше max_duration_min")

    # Валидация дубликатов: только для задач с allow_multi_per_block
    from collections import Counter
    task_counts = Counter(data.task_ids)
    for tid, count in task_counts.items():
        if count > 1:
            task = await get_task(session, tid, allowed.telegram_id)
            if task and not task.allow_multi_per_block:
                raise HTTPException(
                    status_code=400,
                    detail=f"Задача «{task.name}» не поддерживает мульти-режим",
                )

    result = await create_block(
        session,
        user_id=allowed.telegram_id,
        task_ids=data.task_ids,
        block_name=data.block_name,
        day=data.day,
        start_time=_str_to_time(data.start_time),
        duration_type=data.duration_type,
        duration_min=data.duration_min,
        min_duration_min=data.min_duration_min,
        max_duration_min=data.max_duration_min,
    )

    # Планируем jobs в scheduler
    try:
        from backend.bot.scheduler import schedule_block_jobs
        from backend.db.crud.users import get_or_create_user
        user = await get_or_create_user(session, allowed.telegram_id)
        await schedule_block_jobs(result["block"], user.timezone or "Europe/Moscow")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Не удалось запланировать jobs: {e}")

    return BlockCreateResponse(
        block=_block_to_response(result["block"]),
        warnings=[BlockWarning(**w) for w in result["warnings"]],
    )


@router.patch("/{block_id}", response_model=BlockUpdateResponse)
async def patch_block(
    block_id: int,
    data: BlockUpdate,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Обновить блок."""
    kwargs = {}
    for k, v in data.model_dump().items():
        if v is not None:
            if k == "start_time":
                kwargs[k] = _str_to_time(v)
            else:
                kwargs[k] = v

    result = await update_block(session, block_id, allowed.telegram_id, **kwargs)
    if result is None:
        raise HTTPException(status_code=404, detail="Блок не найден")

    # Перепланируем jobs при обновлении
    try:
        from backend.bot.scheduler import cancel_block_jobs, schedule_block_jobs
        from backend.db.crud.users import get_or_create_user
        cancel_block_jobs(block_id)
        if result["block"].status == "planned":
            user = await get_or_create_user(session, allowed.telegram_id)
            await schedule_block_jobs(result["block"], user.timezone or "Europe/Moscow")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Не удалось перепланировать jobs: {e}")

    return BlockUpdateResponse(
        block=_block_to_response(result["block"]),
        is_active=result["is_active"],
    )


@router.delete("/clear")
async def clear_blocks_route(
    week_start: date = Query(...),
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Удалить все planned блоки за неделю (не трогать active/done/failed)."""
    week_end = week_start + timedelta(days=6)
    result = await session.execute(
        select(TaskBlock).where(
            TaskBlock.user_id == allowed.telegram_id,
            TaskBlock.day >= week_start,
            TaskBlock.day <= week_end,
            TaskBlock.status == "planned",
        )
    )
    blocks_to_delete = list(result.scalars().all())
    count = len(blocks_to_delete)

    # Отменяем все jobs
    try:
        from backend.bot.scheduler import cancel_block_jobs
        for block in blocks_to_delete:
            cancel_block_jobs(block.id)
    except Exception:
        pass

    for block in blocks_to_delete:
        await session.delete(block)
    await session.flush()
    return {"deleted": count, "message": f"Удалено {count} блоков"}


@router.delete("/{block_id}")
async def delete_block_route(
    block_id: int,
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Удалить блок."""
    # Отменяем jobs перед удалением
    try:
        from backend.bot.scheduler import cancel_block_jobs
        cancel_block_jobs(block_id)
    except Exception:
        pass

    deleted = await delete_block(session, block_id, allowed.telegram_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Блок не найден")
    return {"ok": True}


@router.post("/auto-create-recurring")
async def auto_create_recurring(
    task_id: int = Query(..., description="ID повторяющейся задачи"),
    week_start: date = Query(..., description="Начало недели (YYYY-MM-DD)"),
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Автоматически создать блоки для повторяющейся задачи на неделю.

    Используется при создании/обновлении recurring задачи с preferred_time:
    - Для каждого recur_day создаёт блок на preferred_time (или ищет свободный слот)
    - Не создаёт дубли если блок на этот день уже есть
    """
    task = await get_task(session, task_id, allowed.telegram_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if not task.is_recurring or not task.recur_days:
        return {"created": 0, "message": "Задача не повторяющаяся"}

    existing_blocks = await list_blocks_for_week(session, allowed.telegram_id, week_start)

    # Собираем дни, где задача уже есть в блоке
    used_days: set[int] = set()
    for b in existing_blocks:
        if task_id in (b.task_ids or []):
            day_offset = (b.day - week_start).days
            used_days.add(day_offset)

    # Расписание по дням
    from backend.db.crud.blocks import get_weekly_schedule
    schedule = await get_weekly_schedule(session, allowed.telegram_id)
    schedule_map = {s.day_of_week: s for s in schedule}

    # Настройки пользователя для fallback
    from backend.db.models import User
    user_result = await session.execute(
        select(User).where(User.telegram_id == allowed.telegram_id)
    )
    user_settings = user_result.scalar_one_or_none()
    default_from = (user_settings.day_start_time if user_settings and user_settings.day_start_time else None) or time(8, 0)
    default_to = (user_settings.day_end_time if user_settings and user_settings.day_end_time else None) or time(23, 50)

    def _get_day_bounds(dow: int) -> tuple[time, time]:
        sched = schedule_map.get(dow)
        if sched:
            return sched.active_from, sched.active_to
        return default_from, default_to

    def _is_slot_free(target_day: date, start: time, duration: int) -> bool:
        day_blocks = [b for b in existing_blocks if b.day == target_day]
        slot_min = start.hour * 60 + start.minute
        end_min = slot_min + duration
        for b in day_blocks:
            b_start = b.start_time.hour * 60 + b.start_time.minute
            b_dur = b.duration_min or b.max_duration_min or 60
            b_end = b_start + b_dur
            if slot_min < b_end and end_min > b_start:
                return False
        return True

    def _find_free_slot(target_day: date, duration: int) -> time | None:
        dow = target_day.weekday()
        slot_start, slot_end = _get_day_bounds(dow)
        day_blocks = [b for b in existing_blocks if b.day == target_day]
        slot_time = slot_start

        while True:
            slot_min = slot_time.hour * 60 + slot_time.minute
            end_min = slot_min + duration
            sched_end_min = slot_end.hour * 60 + slot_end.minute
            if end_min > sched_end_min:
                return None

            overlap = False
            for b in day_blocks:
                b_start = b.start_time.hour * 60 + b.start_time.minute
                b_dur = b.duration_min or b.max_duration_min or 60
                b_end = b_start + b_dur
                if slot_min < b_end and end_min > b_start:
                    overlap = True
                    new_min = b_end
                    if new_min >= 24 * 60:
                        return None
                    slot_time = time(new_min // 60, new_min % 60)
                    break

            if not overlap:
                return slot_time

    duration = task.estimated_time_min or 30
    created_count = 0

    for day_offset in range(7):
        current_day = week_start + timedelta(days=day_offset)
        dow = current_day.weekday()

        if dow not in (task.recur_days or []):
            continue

        if day_offset in used_days:
            continue

        # Пробуем preferred_time, потом свободный слот
        chosen_time = None
        if task.preferred_time and _is_slot_free(current_day, task.preferred_time, duration):
            chosen_time = task.preferred_time
        else:
            chosen_time = _find_free_slot(current_day, duration)

        if chosen_time is not None:
            result = await create_block(
                session,
                user_id=allowed.telegram_id,
                task_ids=[task.id],
                day=current_day,
                start_time=chosen_time,
                duration_type="fixed",
                duration_min=duration,
            )
            existing_blocks.append(result["block"])
            used_days.add(day_offset)
            created_count += 1

    return {"created": created_count, "message": f"Создано {created_count} блоков"}


@router.post("/auto-distribute")
async def auto_distribute(
    week_start: date = Query(...),
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Авто-распределение задач из бэклога на неделю.

    Логика:
    - Эпики (группы задач, is_epic=True) пропускаются — они не задачи
    - Регулярные задачи (is_recurring=True) ставятся на указанные recur_days
    - Обычные задачи ставятся на ближайший свободный слот по приоритету
    """
    from backend.db.crud.blocks import get_weekly_schedule

    # Получаем задачи, отсортированные по приоритету
    tasks = await list_tasks(session, allowed.telegram_id, sort_by="priority")
    existing_blocks = await list_blocks_for_week(session, allowed.telegram_id, week_start)
    schedule = await get_weekly_schedule(session, allowed.telegram_id)

    # Собираем task_ids уже в блоках на этой неделе
    used_task_ids: dict[int, set[int]] = {}  # task_id -> set of day_offsets
    for b in existing_blocks:
        for tid in (b.task_ids or []):
            if tid not in used_task_ids:
                used_task_ids[tid] = set()
            day_offset = (b.day - week_start).days
            used_task_ids[tid].add(day_offset)

    # Расписание по дням недели
    schedule_map = {s.day_of_week: s for s in schedule}

    # Получаем настройки пользователя
    from backend.db.models import User
    from sqlalchemy import select as sa_select
    user_result = await session.execute(
        sa_select(User).where(User.telegram_id == allowed.telegram_id)
    )
    user_settings = user_result.scalar_one_or_none()
    default_from = (user_settings.day_start_time if user_settings and user_settings.day_start_time else None) or time(8, 0)
    default_to = (user_settings.day_end_time if user_settings and user_settings.day_end_time else None) or time(23, 50)

    def _is_day_off(dow: int) -> bool:
        """Проверить, является ли день выходным."""
        sched = schedule_map.get(dow)
        return sched.is_day_off if sched else True

    def _get_day_bounds(dow: int) -> tuple[time, time]:
        """Получить рабочие часы для дня недели.

        Всегда использует часы из расписания (active_from/active_to),
        даже для выходных — чтобы не ставить блоки на 06:30.
        Если расписания нет — fallback на настройки пользователя.
        """
        sched = schedule_map.get(dow)
        if sched:
            return sched.active_from, sched.active_to
        return default_from, default_to

    def _find_free_slot(target_day: date, duration: int) -> time | None:
        """Найти свободный слот на конкретный день."""
        dow = target_day.weekday()
        slot_start, slot_end = _get_day_bounds(dow)

        day_blocks = [b for b in existing_blocks if b.day == target_day]
        slot_time = slot_start

        while True:
            slot_min = slot_time.hour * 60 + slot_time.minute
            end_min = slot_min + duration
            sched_end_min = slot_end.hour * 60 + slot_end.minute

            if end_min > sched_end_min:
                return None

            overlap = False
            for b in day_blocks:
                b_start = b.start_time.hour * 60 + b.start_time.minute
                b_dur = b.duration_min or b.max_duration_min or 60
                b_end = b_start + b_dur
                if slot_min < b_end and end_min > b_start:
                    overlap = True
                    new_min = b_end
                    if new_min >= 24 * 60:
                        return None
                    slot_time = time(new_min // 60, new_min % 60)
                    break

            if not overlap:
                return slot_time

    created_count = 0

    def _is_slot_free(target_day: date, start: time, duration: int) -> bool:
        """Проверить, свободен ли конкретный слот."""
        day_blocks = [b for b in existing_blocks if b.day == target_day]
        slot_min = start.hour * 60 + start.minute
        end_min = slot_min + duration
        for b in day_blocks:
            b_start = b.start_time.hour * 60 + b.start_time.minute
            b_dur = b.duration_min or b.max_duration_min or 60
            b_end = b_start + b_dur
            if slot_min < b_end and end_min > b_start:
                return False
        return True

    # 1. Размещаем регулярные задачи на их recur_days
    # Мелкие задачи (≤10 мин, allow_grouping=true, общий epic_id) — группируем
    MAX_SMALL_TASK_MIN = 10
    MAX_GROUP_BLOCK_MIN = 30
    recurring_tasks = [t for t in tasks if t.is_recurring and not t.is_epic and t.recur_days]

    # Разделяем: крупные и мелкие (группируемые)
    big_recurring = [t for t in recurring_tasks
                     if not t.allow_grouping or (t.estimated_time_min or 30) > MAX_SMALL_TASK_MIN]
    small_recurring = [t for t in recurring_tasks
                       if t.allow_grouping and (t.estimated_time_min or 30) <= MAX_SMALL_TASK_MIN]

    # 1a. Крупные recurring — каждая отдельным блоком
    for task in big_recurring:
        duration = task.estimated_time_min or 30
        for day_offset in range(7):
            current_day = week_start + timedelta(days=day_offset)
            dow = current_day.weekday()

            if dow not in (task.recur_days or []):
                continue
            if task.id in used_task_ids and day_offset in used_task_ids[task.id]:
                continue

            chosen_time = None
            if task.preferred_time and _is_slot_free(current_day, task.preferred_time, duration):
                chosen_time = task.preferred_time
            else:
                chosen_time = _find_free_slot(current_day, duration)

            if chosen_time is not None:
                result = await create_block(
                    session,
                    user_id=allowed.telegram_id,
                    task_ids=[task.id],
                    day=current_day,
                    start_time=chosen_time,
                    duration_type="fixed",
                    duration_min=duration,
                )
                existing_blocks.append(result["block"])
                if task.id not in used_task_ids:
                    used_task_ids[task.id] = set()
                used_task_ids[task.id].add(day_offset)
                created_count += 1

    # 1b. Мелкие recurring — группируем по epic_id/category_id и дню
    from collections import defaultdict

    # Для каждого дня собираем мелкие задачи по группам
    for day_offset in range(7):
        current_day = week_start + timedelta(days=day_offset)
        dow = current_day.weekday()

        # Собираем задачи для этого дня, группируем по epic/category + временной бакет
        day_groups: dict[str, list] = defaultdict(list)
        for task in small_recurring:
            if dow not in (task.recur_days or []):
                continue
            if task.id in used_task_ids and day_offset in used_task_ids[task.id]:
                continue
            dt = task.device_type or "other"
            tb = _preferred_time_bucket(task.preferred_time)
            key = f"epic_{task.epic_id}_{dt}_{tb}" if task.epic_id else f"cat_{task.category_id}_{dt}_{tb}"
            day_groups[key].append(task)

        for group_key, group_tasks in day_groups.items():
            if len(group_tasks) < 2:
                # Одиночная мелкая задача — ставим как обычный блок
                task = group_tasks[0]
                duration = task.estimated_time_min or 5
                chosen_time = None
                if task.preferred_time and _is_slot_free(current_day, task.preferred_time, duration):
                    chosen_time = task.preferred_time
                else:
                    chosen_time = _find_free_slot(current_day, duration)
                if chosen_time is not None:
                    result = await create_block(
                        session,
                        user_id=allowed.telegram_id,
                        task_ids=[task.id],
                        day=current_day,
                        start_time=chosen_time,
                        duration_type="fixed",
                        duration_min=duration,
                    )
                    existing_blocks.append(result["block"])
                    if task.id not in used_task_ids:
                        used_task_ids[task.id] = set()
                    used_task_ids[task.id].add(day_offset)
                    created_count += 1
                continue

            # Группа ≥2 задач — создаём смешанный блок
            # Разбиваем на батчи по MAX_GROUP_BLOCK_MIN
            batch: list = []
            batch_duration = 0
            batches: list[list] = []
            for task in group_tasks:
                task_dur = task.estimated_time_min or 5
                if batch_duration + task_dur > MAX_GROUP_BLOCK_MIN and batch:
                    batches.append(batch)
                    batch = []
                    batch_duration = 0
                batch.append(task)
                batch_duration += task_dur
            if batch:
                batches.append(batch)

            for b in batches:
                b_ids = [t.id for t in b]
                b_duration = sum(t.estimated_time_min or 5 for t in b)

                # Имя блока — от эпика или категории
                # Парсим ключ: epic_{id}_{dt}_{tb} или cat_{id}_{dt}_{tb}
                key_parts = group_key.split("_")
                if key_parts[0] == "epic":
                    epic_id_val = int(key_parts[1])
                    epic_task = next((t for t in tasks if t.id == epic_id_val), None)
                    if epic_task:
                        emoji = epic_task.epic_emoji or "📦"
                        block_name = f"{emoji} {epic_task.name}"
                    else:
                        block_name = "Мини-задачи"
                else:
                    cat_id = int(key_parts[1])
                    from backend.db.models import Category
                    cat_result = await session.execute(
                        select(Category).where(Category.id == cat_id)
                    )
                    cat = cat_result.scalar_one_or_none()
                    block_name = f"{cat.emoji or '📋'} {cat.name}" if cat else "Мини-задачи"

                # Preferred time — берём самое раннее из группы
                pref = _earliest_preferred_time(b)
                chosen_time = None
                if pref and _is_slot_free(current_day, pref, b_duration):
                    chosen_time = pref
                else:
                    chosen_time = _find_free_slot(current_day, b_duration)

                if chosen_time is not None:
                    result = await create_block(
                        session,
                        user_id=allowed.telegram_id,
                        task_ids=b_ids,
                        block_name=block_name,
                        day=current_day,
                        start_time=chosen_time,
                        duration_type="fixed",
                        duration_min=b_duration,
                    )
                    existing_blocks.append(result["block"])
                    for task in b:
                        if task.id not in used_task_ids:
                            used_task_ids[task.id] = set()
                        used_task_ids[task.id].add(day_offset)
                    created_count += 1

    # 2. Автогруппировка мелких НЕрекурсивных задач (≤10 мин, allow_grouping=true)
    small_tasks = [
        t for t in tasks
        if not t.is_recurring and not t.is_epic and t.id not in used_task_ids
        and t.allow_grouping
        and (t.estimated_time_min or 30) <= MAX_SMALL_TASK_MIN
    ]

    # Группируем: по epic_id/category_id + временной бакет preferred_time
    groups: dict[str, list] = defaultdict(list)
    for task in small_tasks:
        dt = task.device_type or "other"
        tb = _preferred_time_bucket(task.preferred_time)
        if task.epic_id:
            key = f"epic_{task.epic_id}_{dt}_{tb}"
        else:
            key = f"cat_{task.category_id}_{dt}_{tb}"
        groups[key].append(task)

    # Собираем блоки из групп (≥2 задачи в группе)
    grouped_task_ids: set[int] = set()
    workdays = [i for i in range(7) if not _is_day_off((week_start + timedelta(days=i)).weekday())]
    offdays = [i for i in range(7) if _is_day_off((week_start + timedelta(days=i)).weekday())]
    day_order = workdays + offdays

    for group_key, group_tasks in groups.items():
        if len(group_tasks) < 2:
            continue  # одиночные мелкие задачи пойдут как обычные

        # Разбиваем группу на подгруппы, помещающиеся в MAX_GROUP_BLOCK_MIN
        batch: list = []
        batch_duration = 0
        batches: list[list] = []

        for task in group_tasks:
            task_dur = task.estimated_time_min or 5
            if batch_duration + task_dur > MAX_GROUP_BLOCK_MIN and batch:
                batches.append(batch)
                batch = []
                batch_duration = 0
            batch.append(task)
            batch_duration += task_dur

        if batch:
            batches.append(batch)

        # Размещаем каждый батч
        for batch in batches:
            if len(batch) < 2:
                continue  # одиночные оставляем для шага 3

            batch_duration = sum(t.estimated_time_min or 5 for t in batch)
            # Мульти-распределение: задачи с allow_multi_per_block заполняют блок дубликатами
            batch_ids = _calculate_multi_distribution(batch, batch_duration)
            # Имя блока: название эпика или категории
            if group_key.startswith("epic_"):
                epic_id_val = int(group_key.split("_")[1])
                epic_task = next((t for t in tasks if t.id == epic_id_val), None)
                if epic_task:
                    emoji = epic_task.epic_emoji or "📦"
                    block_name = f"{emoji} {epic_task.name}"
                else:
                    block_name = "Мини-задачи"
            else:
                cat_id = int(group_key.split("_")[1])
                from backend.db.models import Category
                cat_result = await session.execute(
                    select(Category).where(Category.id == cat_id)
                )
                cat = cat_result.scalar_one_or_none()
                block_name = f"{cat.emoji or '📋'} {cat.name}" if cat else "Мини-задачи"

            # Preferred time — берём самое раннее из батча
            batch_pref = _earliest_preferred_time(batch)

            for day_offset in day_order:
                current_day = week_start + timedelta(days=day_offset)
                free_time = None
                if batch_pref and _is_slot_free(current_day, batch_pref, batch_duration):
                    free_time = batch_pref
                else:
                    free_time = _find_free_slot(current_day, batch_duration)
                if free_time is not None:
                    result = await create_block(
                        session,
                        user_id=allowed.telegram_id,
                        task_ids=batch_ids,
                        block_name=block_name,
                        day=current_day,
                        start_time=free_time,
                        duration_type="fixed",
                        duration_min=batch_duration,
                    )
                    existing_blocks.append(result["block"])
                    grouped_task_ids.update(batch_ids)
                    created_count += 1
                    break

    # 3. Затем размещаем обычные задачи (не recurring, не эпики, не сгруппированные)
    regular_tasks = [
        t for t in tasks
        if not t.is_recurring and not t.is_epic
        and t.id not in used_task_ids and t.id not in grouped_task_ids
    ]

    for task in regular_tasks:
        duration = task.estimated_time_min or 30

        for day_offset in day_order:
            current_day = week_start + timedelta(days=day_offset)

            # Если у задачи есть preferred_time — пробуем только этот слот (±30 мин)
            if task.preferred_time:
                if _is_slot_free(current_day, task.preferred_time, duration):
                    free_time = task.preferred_time
                else:
                    continue  # На этот день нет подходящего слота
            else:
                free_time = _find_free_slot(current_day, duration)

            if free_time is not None:
                result = await create_block(
                    session,
                    user_id=allowed.telegram_id,
                    task_ids=[task.id],
                    day=current_day,
                    start_time=free_time,
                    duration_type="fixed",
                    duration_min=duration,
                )
                existing_blocks.append(result["block"])
                created_count += 1
                break

    return {"distributed": created_count, "message": f"Распределено {created_count} задач"}


@router.post("/carry-over")
async def carry_over(
    from_week: date = Query(..., description="Начало текущей недели"),
    allowed: AllowedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Перенести невыполненные блоки на следующую неделю."""
    blocks = await list_blocks_for_week(session, allowed.telegram_id, from_week)
    next_week = from_week + timedelta(days=7)

    carried = 0
    for block in blocks:
        if block.status in ("planned", "failed"):
            # Определяем день недели и ставим на тот же день следующей недели
            day_offset = (block.day - from_week).days
            new_day = next_week + timedelta(days=day_offset)

            await create_block(
                session,
                user_id=allowed.telegram_id,
                task_ids=block.task_ids,
                block_name=block.block_name,
                day=new_day,
                start_time=block.start_time,
                duration_type=block.duration_type,
                duration_min=block.duration_min,
                min_duration_min=block.min_duration_min,
                max_duration_min=block.max_duration_min,
            )
            carried += 1

    return {"carried": carried, "message": f"Перенесено {carried} блоков на следующую неделю"}

# Changelog — Task Planner Bot

Лог изменений по этапам и батчам. Помогает новым агентам быстро понять что уже сделано.

---

## Этапы 1-7 (базовая реализация) — ЗАВЕРШЕНЫ

### Этап 1: Скелет проекта + Конфигурация + Модели БД
- `.env.example`, `backend/config.py` (pydantic-settings)
- `backend/db/database.py` — async engine, sessionmaker, `init_db()` с миграциями
- `backend/db/models.py` — все 9 таблиц (allowed_users, users, categories, weekly_schedule, weekly_goals, tasks, task_blocks, spam_config, logs)
- WAL mode, foreign keys для SQLite

### Этап 2: CRUD + FastAPI
- `backend/db/crud/` — users, tasks, blocks, admin
- `backend/api/deps.py` — авторизация по X-Telegram-User-Id
- `backend/api/schemas.py` — Pydantic v2 схемы
- `backend/api/routes/` — users, categories
- `backend/main.py` — FastAPI app с CORS, lifespan

### Этап 3: Скелет бота
- `backend/bot/` — Bot + Dispatcher, middleware whitelist
- `/start`, `/help`, `/admin` хэндлеры
- Polling/webhook режимы

### Этап 4: Полный API
- `routes/tasks.py` — CRUD с фильтрами, soft delete
- `routes/blocks.py` — CRUD блоков, auto-distribute, carry-over, overlap warnings
- `routes/schedule.py` — GET/PUT расписания
- `routes/stats.py` — статистика за неделю
- `routes/goals.py` — цели по категориям

### Этап 5: Команды бота
- `/stop`, `/pause`, `/resume`, `/settings`, `/stats`

### Этап 6: Фронтенд — скелет + Экраны 0-3
- React + TypeScript + Vite, Zustand store
- Тёмная тема, CSS variables, mobile-first
- Экран 0: TimezoneSelect
- Экран 1: Categories (CRUD + drag-to-reorder)
- Экран 2: WeekSchedule (7 дней, тихое время, спам)
- Экран 3: Goals (слайдеры)
- UI: Button, Dialog, TimePicker, BottomNav

### Этап 7: Фронтенд — Экраны 4-6
- Экран 4: Backlog — CRUD задач, фильтры, эпики
- Экран 5: Calendar — drag & drop (@dnd-kit), 3 типа блоков
- Экран 6: Summary — recharts графики
- Settings экран

---

## Batch 1: UX-фиксы (5 исправлений) — ЗАВЕРШЁН

1. **Сегодня подсвечивается** в заголовке календаря (синий фон)
2. **Выходные дни** отмечаются «вых» в заголовке
3. **Шаг таймпикеров** — 30 мин вместо 1 мин в WeekSchedule
4. **Длительность блока вместо задачи** — блок в календаре показывает свою duration, а не задачи
5. **Время по формату расписания** — часы блока отображаются из schedule active_from/active_to

---

## Batch 2: UX-фиксы (5 исправлений) — ЗАВЕРШЁН

1. **func.case() баг** — исправлен SQL для сортировки задач по приоритету
2. **Подсказки и пояснения** — добавлены hint-тексты ко всем полям формы бэклога
3. **Список задач под эпиком** — вложенные задачи видны при раскрытии эпика
4. **Settings/WeekSchedule/Goals — ручное сохранение** — убрано авто-сохранение, добавлен диалог «Несохранённые изменения» при навигации. Zustand store: `hasUnsavedChanges`, `pendingScreen`, `confirmNavigation`, `cancelNavigation`
5. **preferred_time для recurring задач** — новое поле в модели Task, UI в форме бэклога, auto-distribute учитывает preferred_time

---

## Batch 3: UX-фиксы (6 исправлений) — ЗАВЕРШЁН

1. **Фиксированная ширина блоков** — `max-width: 180px` для `.cal-block`, мобильный override
2. **Расширение временных рамок календаря** — `useMemo` сканирует блоки за пределами `day_start_time`/`day_end_time` и расширяет шкалу
3. **Авто-создание блоков для recurring задач** — при сохранении recurring задачи с recur_days автоматически создаются блоки через `POST /blocks/auto-create-recurring`
4. **Кнопка «Очистить» в календаре** — `DELETE /blocks/clear` удаляет только planned блоки за неделю (не из бэклога), с диалогом подтверждения
5. **Автогруппировка мелких задач** — при auto-distribute мелкие задачи (≤10 мин, `allow_grouping=true`, общий epic/category) группируются в смешанные блоки. Работает и для recurring, и для обычных задач
6. **Группа задач выше категории в форме** — селектор эпика перемещён выше категории, при выборе группы — авто-установка категории

---

## Файлы, изменённые в каждом батче

### Batch 2 ключевые файлы:
- `frontend/src/store/index.ts` — unsaved changes guard
- `frontend/src/App.tsx` — глобальный диалог unsaved changes
- `frontend/src/components/Settings/Settings.tsx` — ручное сохранение
- `frontend/src/components/WeekSchedule/WeekSchedule.tsx` — ручное сохранение
- `frontend/src/components/Goals/Goals.tsx` — ручное сохранение
- `backend/db/models.py` — preferred_time колонка
- `backend/api/schemas.py` — preferred_time в TaskCreate/Update/Response
- `backend/api/routes/tasks.py` — конвертация preferred_time

### Batch 3 ключевые файлы:
- `frontend/src/components/Calendar/Calendar.tsx` — effectiveStart/End, clear button, clear dialog
- `frontend/src/components/Calendar/Calendar.css` — max-width для блоков
- `frontend/src/components/Backlog/Backlog.tsx` — epic выше category, autoCreateRecurring
- `frontend/src/api/client.ts` — clearBlocks, autoCreateRecurring
- `backend/api/routes/blocks.py` — DELETE /clear, POST /auto-create-recurring, группировка в auto-distribute

## Batch 3.1: Дополнительные фичи — ЗАВЕРШЁН

1. **CHANGELOG.md** — создан лог всех изменений для новых агентов
2. **Эмодзи для групп задач** — новое поле `epic_emoji` в модели Task, эмодзи-инпут в форме создания/редактирования группы, отображение в списке и селекторе
3. **Чекбокс «Мульти-задача»** — новое поле `allow_multi_per_block` в модели Task. Пояснение: «Несколько экземпляров задачи в одном блоке (например, 5 уроков подряд)»
4. **Имя блока с эмодзи** — при автогруппировке имя блока включает epic_emoji (например, «🇬🇧 Английский» вместо «Английский»)

### Batch 3.1 ключевые файлы:
- `backend/db/models.py` — `allow_multi_per_block`, `epic_emoji` колонки
- `backend/db/database.py` — 2 новые миграции
- `backend/api/schemas.py` — новые поля в TaskCreate/Update/Response
- `frontend/src/types/index.ts` — `allow_multi_per_block`, `epic_emoji` в Task
- `frontend/src/components/Backlog/Backlog.tsx` — emoji input для эпиков, мульти-задача чекбокс
- `backend/api/routes/blocks.py` — epic_emoji в именах блоков при автогруппировке

---

## Batch 4: Мульти-задачи + device_type + эпик-drag — ЗАВЕРШЁН

### Новая функциональность:
1. **device_type** — новое поле задачи: `desktop` / `mobile` / `other` (default: other). Задачи группируются только с одинаковым device_type. UI: 3 кнопки (💻/📱/🔧) в форме бэклога
2. **Мульти-задачная логика в BlockForm** — при перетаскивании одной задачи с `allow_multi_per_block`: показ `task ×N` (N = block_size / task_duration). Для группы задач: взвешенное распределение по приоритету (high=3, medium=2, low=1). Превью распределения в форме
3. **task_ids с дубликатами** — массив `task_ids` поддерживает повторы: `[7, 7, 7, 9, 9]`. `is_mixed` определяется по уникальным ID. Имя блока: `Counter` для формата `Task x3, Task2 x2`
4. **Валидация дубликатов** — `POST /blocks` проверяет `allow_multi_per_block` для задач с count > 1
5. **Группировка по device_type** — ключи группировки в auto-distribute: `epic_{id}_{dt}` / `cat_{id}_{dt}`
6. **Эпик-drag из BacklogPanel** — заголовки эпиков перетаскиваются из панели бэклога в календарь. DraggableEpic компонент, DragOverlay с превью, handleDragEnd открывает BlockForm со всеми задачами эпика
7. **Мульти-блок отображение в DayColumn** — смешанные блоки показывают уникальные задачи с `×N` вместо просто «N задач»
8. **_calculate_multi_distribution** — бэкенд-функция для взвешенного распределения мульти-задач в auto-distribute
9. **preferred_time constraint** — задачи с preferred_time при auto-distribute размещаются только в matching слоты

### Batch 4 ключевые файлы:
- `backend/db/models.py` — `device_type` колонка
- `backend/db/database.py` — миграция device_type
- `backend/api/schemas.py` — device_type в TaskCreate/Update/Response + validators
- `backend/api/routes/blocks.py` — `_calculate_multi_distribution`, `_is_preferred_time_match`, валидация дубликатов, группировка по device_type, preferred_time constraint
- `backend/db/crud/blocks.py` — Counter-based block naming, is_mixed по unique IDs
- `frontend/src/types/index.ts` — device_type в Task
- `frontend/src/components/Backlog/Backlog.tsx` — device_type selector (💻/📱/🔧)
- `frontend/src/components/Calendar/BlockForm.tsx` — полная переработка: multiCounts, autoDistribution, deviceTypeWarning, preferredTimeWarnings
- `frontend/src/components/Calendar/BacklogPanel.tsx` — DraggableEpic, группировка по эпикам
- `frontend/src/components/Calendar/Calendar.tsx` — dragEpic state, handleDragEnd для эпиков, DragOverlay для эпиков
- `frontend/src/components/Calendar/DayColumn.tsx` — formatMultiTasks (×N отображение)

---

## Batch 5: UX-фиксы (5 исправлений) — ЗАВЕРШЁН

1. **Компактный календарь** — слоты 24px (было 32px), блоки с уменьшенными padding/font-size, убран max-width. 7 дней гарантированно влезают в экран
2. **Эмодзи-пикер для групп задач** — сетка 8x4 с популярными эмодзи (флаги, иконки) вместо текстового инпута
3. **Авто-рандомное распределение мульти-задач** — повторы рассчитываются автоматически рандомом на основе приоритета. Кнопка «🎲 Перемешать» для ре-рандома. Сумма всегда ≤ длительность блока
4. **Шире инпут повторов** — 70px (было 55px) для двузначных чисел
5. **Блоки показывают «N задач»** — вместо полного списка имён задач, компактнее для календаря

### Batch 5 ключевые файлы:
- `frontend/src/components/Calendar/Calendar.css` — компактные слоты и блоки
- `frontend/src/components/Calendar/DayColumn.tsx` — slot height 24px, «N задач» вместо имён
- `frontend/src/components/Calendar/BlockForm.tsx` — рандомное распределение, кнопка перемешать, шире инпут
- `frontend/src/components/Backlog/Backlog.tsx` — EPIC_EMOJI_LIST, emoji picker grid

---

## Batch 6: UX-фиксы (3 исправления) — ЗАВЕРШЁН

1. **Колонки календаря = заголовки** — `minmax(0, 1fr)` вместо `1fr`, `min-width: 0` + `overflow: hidden` на day-column. Блоки теперь строго по ширине заголовков дней
2. **Полный эмодзи-пикер** — общий компонент `EmojiPicker` с 9 вкладками (Частые, Люди, Природа, Еда, Активности, Путешествия, Вещи, Символы, Флаги). Используется и в категориях, и в группах задач
3. **«N задач» в блоках** — для блоков с несколькими задачами показывается «📦 N задач» вместо названия. Тултип с полной информацией при наведении

### Batch 6 ключевые файлы:
- `frontend/src/components/EmojiPicker.tsx` — новый общий компонент эмодзи-пикера
- `frontend/src/components/Categories/Categories.tsx` — переключен на EmojiPicker
- `frontend/src/components/Categories/Categories.css` — стили для emoji-picker-full/tabs/grid
- `frontend/src/components/Backlog/Backlog.tsx` — переключен на EmojiPicker, убран EPIC_EMOJI_LIST
- `frontend/src/components/Calendar/Calendar.css` — minmax(0,1fr), day-column overflow
- `frontend/src/components/Calendar/DayColumn.tsx` — «📦 N задач» в первой строке, тултип

---

## Batch 7: Scheduler + Напоминания + Callbacks — ЗАВЕРШЁН

Полная система уведомлений через Telegram: scheduler, напоминания, спам-машина, pomodoro, итог дня.

### Новые файлы:
1. **`backend/bot/scheduler.py`** — APScheduler (AsyncIOScheduler):
   - `init_scheduler()` — запуск scheduler при старте
   - `schedule_block_jobs()` — планирование всех jobs для блока (prep, start, end, min/max_duration, pomodoro)
   - `cancel_block_jobs()` — отмена всех jobs блока
   - `restore_jobs_on_startup()` — восстановление planned/active блоков при рестарте
   - `schedule_day_summary()` — итог дня с учётом тихого времени
   - `_is_in_quiet_time()` — проверка тихого времени (с поддержкой перехода через полночь)

2. **`backend/bot/reminders.py`** — все типы уведомлений:
   - `send_prep_reminder()` — за N мин до старта (подготовка)
   - `send_start_reminder()` — старт блока (разный текст для fixed/open/range)
   - `send_block_end_questionnaire()` — опросник: Выполнено/Частично/Не выполнено
   - `send_min_duration_reached()` — минимум прошёл (range)
   - `send_max_duration_reminder()` — превышение max_duration (open/range)
   - `send_pomodoro_break()` / `send_pomodoro_resume()` — циклы 25+5 мин
   - `send_day_summary()` — итог дня с категориями и статистикой
   - `send_restart_active_block_notification()` — уведомление при рестарте для активных блоков
   - Спам-машина: `_maybe_start_spam()`, `_start_spam_loop()`, `stop_spam_and_cleanup()`
     - Тройная проверка: spam_config.enabled AND категория AND task.spam_enabled
     - Экспоненциальный интервал (initial × multiplier, до max)
     - Не спамит в тихое время и вне рабочих часов
     - Удаляет все спам-сообщения при ответе пользователя

3. **`backend/bot/handlers/callbacks.py`** — inline-кнопки:
   - `block_finish:{id}` — завершить (open/range)
   - `block_finish_early:{id}` — завершить досрочно (fixed/range)
   - `quest_done/partial/failed:{id}` — опросник завершения
   - `reason:*:{id}` — причины: Не успел, Отвлёкся, Неактуально, Другое
   - FSM для произвольной причины (force_reply)
   - Любое сообщение во время спама → стоп спам + повтор опросника

### Изменённые файлы:
- `backend/main.py` — интеграция scheduler (init, restore_jobs, shutdown)
- `backend/bot/__init__.py` — подключение callbacks router
- `backend/api/routes/blocks.py` — schedule/cancel jobs при CRUD блоков
- `backend/db/crud/users.py` — `get_all_active_users()` для восстановления

---

## Batch 7.1: Пост-фиксы — ЗАВЕРШЁН

1. **Inline-редактирование настроек задачи в BlockForm** — при выборе задачи в форме блока можно менять: спам (📢), помодоро (🍅), повтор (🔁) + дни недели. Изменения сохраняются в фоне через API без закрытия диалога
2. **Быстрые кнопки дедлайна** — при создании задачи с дедлайном: «Сегодня», «Завтра», «Конец недели» (последний рабочий день из расписания)
3. **Сортировка в BacklogPanel** — 5 режимов: по приоритету (🔴), дедлайну (📅), категории (📁), имени (🔤), времени (⏱). Индикаторы приоритета (🔴/🟢) на задачах
4. **Localhost кнопка /start** — для локальной разработки вместо WebApp-кнопки (требует HTTPS) используется обычная URL-кнопка

### Batch 7.1 ключевые файлы:
- `frontend/src/components/Calendar/BlockForm.tsx` — localTasks state, inline settings
- `frontend/src/components/Backlog/Backlog.tsx` — deadline quick buttons
- `frontend/src/components/Calendar/BacklogPanel.tsx` — sortMode state, sortTasks(), sort bar UI
- `frontend/src/components/Calendar/Calendar.css` — backlog-sort-bar/btn styles
- `backend/bot/handlers/start.py` — URL button for localhost

---

## Batch 7.2: Команды /plan и /next — ЗАВЕРШЁН

1. **`/plan`** — план на день с опциями: `/plan`, `/plan завтра`, `/plan 2`, `/plan неделя`
2. **`/next`** — ближайший предстоящий блок с деталями задач и временем до старта
3. Обновлён `/help` с новыми командами
4. Команды зарегистрированы в BotFather

### Batch 7.2 ключевые файлы:
- `backend/bot/handlers/plan.py` — НОВЫЙ: /plan и /next
- `backend/bot/__init__.py` — подключение plan router, BotCommand
- `backend/bot/handlers/start.py` — обновлённый /help

---

## Batch 7.3: Админ-панель по username + кнопки выбора — ЗАВЕРШЁН

1. **Поиск по @username** — в /admin действиях (удаление, вкл/выкл, статистика) теперь можно вводить @username вместо числового ID
2. **Кнопки выбора пользователя** — для удаления/вкл-выкл/статистики показываются inline-кнопки со списком пользователей (кроме самого админа)
3. **Авто-обновление username** — middleware сохраняет username и first_name из каждого сообщения/callback пользователя
4. **`resolve_user_input()`** — универсальная CRUD-функция: принимает числовой ID или @username (с/без @)
5. **Отображение @username** — в списке и статистике показывается @username вместо числового ID

### Batch 7.3 ключевые файлы:
- `backend/bot/handlers/admin.py` — полная переработка: inline-кнопки, username input, _user_display
- `backend/db/crud/users.py` — `get_allowed_user_by_username()`, `resolve_user_input()`
- `backend/bot/middlewares.py` — авто-обновление username/first_name

---

## Batch 8: UX-фиксы (5 исправлений) — ЗАВЕРШЁН

1. **Failed блок → planned при перетаскивании** — перемещение блока со статусом `failed`/`skipped` на новый слот сбрасывает статус в `planned`
2. **DragOverlay по размеру блока** — при перетаскивании блока overlay соответствует его реальному размеру (высота = slotsCount × 28 - 2px), а не большой пилюле
3. **Гибридная коллизия при перетаскивании** — `pointerWithin` + `closestCenter` fallback. Решает проблему «перетаскивание случайно перестаёт работать» при узких колонках
4. **Убран ×N в /plan** — для мульти-задач `/plan` показывает уникальные имена задач (без дубликатов `x3`)
5. **`/next` переименован** — «Ближайшая задача» → «Ближайший блок», добавлен подсчёт задач в блоке

### Batch 8 ключевые файлы:
- `backend/db/crud/blocks.py` — status reset при перетаскивании
- `backend/bot/handlers/plan.py` — unique task names, /next block naming
- `backend/bot/handlers/start.py` — /help text update
- `frontend/src/components/Calendar/Calendar.tsx` — hybridCollision, block-sized DragOverlay

---

## Batch 9: Сортировки, группировки, табличный вид — ЗАВЕРШЁН

1. **Backlog: секции «Регулярные/Разовые»** — collapsible секции с chevron + count badge. Задачи группируются по `is_recurring` → внутри каждой секции эпики и standalone
2. **Backlog: 6 полей сортировки** — приоритет, дедлайн, категория, имя, время, дата создания. Повторный клик — reverse (↑/↓)
3. **Backlog: переключатель карточки/таблица** — кнопки ▦/☰ рядом с сортировкой. Табличный вид: приоритет, название, группа, категория, время, дедлайн, кнопка удаления
4. **BacklogPanel (календарь): секции «Регулярные/Разовые»** — аналогичные collapsible секции в боковой панели календаря
5. **BlockForm: сортировка задач** — 4 кнопки (🔴📁🔤⏱) для сортировки списка задач при создании блока
6. **BlockForm: 3 режима группировки** — по типу (🔁 рег/разовые), по категории (📁), по эпику (📦). Переключатель в шапке списка
7. **BlockForm: чекбокс на группе** — клик по чекбоксу группы выделяет/снимает все задачи разом. Поддержка indeterminate-состояния
8. **Убран drag hint баннер** — «Перетащите блок на новый слот» больше не появляется
9. **BlockForm: мульти-задачи** — скрытие кнопки «Перемешать» когда нет места для доп. повторов, подсказка «Увеличьте длительность блока»
10. **Fix Backlog crash** — `catMap` useMemo перемещён перед зависимыми useMemos (sortTaskList, buildEpicGroups)

### Batch 9 ключевые файлы:
- `frontend/src/components/Backlog/Backlog.tsx` — sortField/sortDir, expandedSections, viewMode, flatSorted, table view
- `frontend/src/components/Backlog/Backlog.css` — sort-bar, section styles, view-toggle, table styles
- `frontend/src/components/Calendar/BacklogPanel.tsx` — recurring/onetime sections, buildGroup
- `frontend/src/components/Calendar/BlockForm.tsx` — taskSortField, groupMode, closedSections, toggleGroupTasks, tasksByCategory, tasksByEpic
- `frontend/src/components/Calendar/Calendar.tsx` — removed drag hint

---

## Batch 10: Access Request + Timezone Picker — ЗАВЕРШЁН

### Новая функциональность:

1. **Система запросов доступа** — неавторизованные пользователи видят кнопку «📩 Отправить запрос» вместо отказа. Админ получает уведомление с кнопками «✅ Одобрить / ❌ Отклонить». Пользователь получает уведомление о результате. При одобрении — автосоздание дефолтных данных (категории, расписание, spam_config)
2. **Timezone picker — выпадающий список** — замена текстового ввода на dropdown с форматом `UTC+X (города)`. 24 строки, 1–3 крупнейших города в каждой. Поиск по городам и offset
3. **DST-разделение строк** — города с разными правилами перевода часов (DST) вынесены в отдельные строки. Маркер 🔄 на строках с переводом часов. Гарантирует корректность IANA-идентификатора при сохранении
4. **Автоопределение + fallback** — браузер определяет TZ через `Intl`, если точного совпадения нет — подбор по UTC offset
5. **Два компонента** — TimezoneSelect (экран первого запуска) и Settings (настройки) используют единый TIMEZONE_DATA

### Batch 10 ключевые файлы:
- `backend/bot/middlewares.py` — WhitelistMiddleware: кнопка «Отправить запрос», обработка callback `access_request:send`
- `backend/bot/handlers/admin.py` — `admin_approve_request()`, `admin_reject_request()`, уведомления пользователю
- `frontend/src/components/Settings/Settings.tsx` — TIMEZONE_DATA с hasDST, dropdown picker, detectedMatch, getUtcOffset
- `frontend/src/components/Settings/Settings.css` — стили tz-picker-*, tz-picker-item-dst
- `frontend/src/components/TimezoneSelect/TimezoneSelect.tsx` — аналогичный TIMEZONE_DATA, detectedMatch логика
- `frontend/src/components/TimezoneSelect/TimezoneSelect.css` — tz-item-dst стиль

---

## Batch 11: Спам для пустых слотов — ЗАВЕРШЁН

Напоминания о незаполненном плане: если в бэклоге есть нераспределённые задачи И в расписании есть свободные слоты — бот напоминает заполнить план.

### Новая функциональность:

1. **Вечернее напоминание** — за 1 час до `day_end_time` проверяет завтрашний день. Если есть свободные слоты (≥30 мин) и нераспределённые задачи — мягкое напоминание с кнопкой «Открыть планировщик»
2. **Утреннее напоминание** — в `active_from` рабочего дня. Повторяется каждые N минут (настраивается), пока слоты не заполнены или не закончится рабочее время
3. **Умная проверка** — учитывает расписание (выходные, рабочие часы), тихое время, тип задач (recurring с recur_days, обычные)
4. **Новые поля spam_config** — `empty_slots_enabled` (вкл/выкл) и `empty_slots_interval_min` (интервал утренних повторов)
5. **UI настройка** — новая секция в WeekSchedule: чекбокс включения + ввод интервала
6. **Восстановление при рестарте** — `restore_jobs_on_startup()` планирует проверку пустых слотов для всех пользователей

### Логика определения «пустого» дня:
- Свободные минуты = рабочее время − сумма длительностей блоков
- Нераспределённые задачи = задачи без блоков на целевой день (recurring только если день в recur_days)
- Напоминание срабатывает ТОЛЬКО если оба условия выполнены

### Batch 11 ключевые файлы:
- `backend/db/models.py` — `empty_slots_enabled`, `empty_slots_interval_min` в SpamConfig
- `backend/db/database.py` — 2 миграции для новых колонок
- `backend/api/schemas.py` — новые поля в SpamConfigResponse/Update
- `backend/db/crud/blocks.py` — `check_empty_slots_and_backlog()` — CRUD проверки
- `backend/bot/reminders.py` — `send_empty_slots_evening_reminder()`, `send_empty_slots_morning_reminder()`
- `backend/bot/scheduler.py` — `schedule_empty_slots_check()`, обновлён `restore_jobs_on_startup()`
- `frontend/src/types/index.ts` — новые поля в SpamConfig
- `frontend/src/components/WeekSchedule/WeekSchedule.tsx` — UI секция «Напоминания о пустых слотах»

---

## Batch 12: Деплой (nginx + systemd + setup.sh) — ЗАВЕРШЁН

Инфраструктура для продакшена на VPS (Ubuntu/Debian) + Cloudflare Pages.

### Архитектура:
```
Cloudflare Pages (*.pages.dev) → React SPA (статика, CDN)
VPS (yourdomain.com)
  nginx (443/80) → reverse proxy → uvicorn (8000)
  systemd → автозапуск + рестарт
  Let's Encrypt → HTTPS
```

### Новые файлы:
1. **`nginx/task-planner.conf`** — reverse proxy: /api/ и /webhook → FastAPI. HTTPS с Let's Encrypt, HTTP→HTTPS редирект, proxy headers, security headers
2. **`systemd/task-planner.service`** — systemd unit: User=taskplanner, venv, Restart=on-failure, ProtectSystem=strict, ReadWritePaths для БД
3. **`setup.sh`** — скрипт первой установки: пакеты, пользователь, venv, pip install, интерактивный ввод (домен, BOT_TOKEN, ADMIN_USER_ID), генерация .env и WEBHOOK_SECRET, certbot SSL, запуск сервиса

### Изменённые файлы:
4. **`frontend/src/api/client.ts`** — `API_BASE` из `import.meta.env.VITE_API_URL` (для Cloudflare Pages фронт на отдельном домене)
5. **`backend/main.py`** — CORS: динамические origins из `FRONTEND_URL`, localhost только при `DEBUG=true`
6. **`.env.example`** — обновлён с комментариями для продакшена и Cloudflare Pages

### Инструкция деплоя (кратко):
```bash
# На VPS:
scp -r . user@server:/tmp/task-planner
ssh user@server
sudo bash /tmp/task-planner/setup.sh
# Вводим: домен, BOT_TOKEN, ADMIN_USER_ID, FRONTEND_URL

# Cloudflare Pages:
# Build command: cd frontend && npm install && npm run build
# Build output: frontend/dist
# Env: VITE_API_URL=https://yourdomain.com/api
```

---

## v1.2.0 — Помодоро-центричная переработка — ЗАВЕРШЁН

Полная переработка архитектуры: от блоков с типами длительности к помодоро-циклам как центральной механике.

### Концепция:
- **Помодоро** — автоматические циклы 25+5 мин весь рабочий день
- **События** (созвоны, встречи) — отдельная сущность, НЕ задача, НЕ в статистике
- **Задачи** имеют статусы (kanban): grooming → in_progress → blocked → done
- Задачи назначаются на день, а не на конкретное время — помодоро управляет

### Step 1: Модели и схемы
- Модель `Event` — name, day, start_time, end_time, category_id, status, reminder_before_min
- `Task` — новые поля: status, scheduled_date, description, link
- `TaskBlock` — упрощён: task_id (один), pomodoro_number
- `User` — настройки помодоро: work_min, short_break_min, long_break_min, cycles_before_long
- Убрано: duration_type, block_name, is_mixed, task_ids (массив), quiet_start/quiet_end
- Pydantic v2 схемы обновлены

### Step 2: API
- `routes/events.py` — полный CRUD для событий (GET по неделе, POST, PATCH, DELETE)
- `routes/tasks.py` — фильтр по status, scheduled_date
- `routes/users.py` — настройки помодоро, reminders_paused_until, reminders_stopped
- Миграции для всех новых колонок

### Step 3: Обработчики бота
- `/settings` — объединяет /stop, /pause, /resume, /admin (всё через inline-кнопки)
- `/plan` — навигация по дням через кнопки, показ событий + задач
- `/backlog` — просмотр задач по статусам, фильтр (сегодня/все), смена статуса, описание+ссылка
- `callbacks.py` — помодоро flow: выбор задачи, пропуск, завершение события, итог дня
- Убрана команда `/next`, переработан `/help`
- 6 команд: start, help, plan, backlog, settings, stats

### Step 4: Scheduler + напоминания
- `scheduler.py` — полная переработка:
  - `schedule_pomodoro_cycle()` — планирует весь день помодоро-циклов по рабочим часам
  - `schedule_event_jobs()` — prep/start/end для событий
  - `restore_jobs_on_startup()` — восстановление циклов и событий
  - `_pomodoro_counts` — трекинг номера помодоро за день
- `reminders.py` — полная переработка:
  - `send_pomodoro_start()` — выбор задачи из назначенных на день
  - `send_pomodoro_end_questionnaire()` — опросник + спам при игноре
  - `send_pomodoro_break()` — короткий или длинный перерыв (каждый 4-й)
  - `send_event_*()` — уведомления о событиях (prep, start, end)
  - `send_day_summary()` — помодоро-статистика + перенос незавершённых задач
  - Раздельный спам для помодоро и событий с разными пулами текстов
  - 40+ спам-текстов с разными сценариями (юмор, философия, мотивация, ультиматумы)

### Step 5: Фронтенд
- `types/index.ts` — Event тип, обновлены Task, TaskBlock, User, WeekStats
- `api/client.ts` — Events CRUD эндпоинты
- `store/index.ts` — events state, loadEvents()
- `Settings.tsx` — настройки помодоро (work/short break/long break/cycles), убрано тихое время
- `Summary.tsx` — помодоро-статистика (done/partial/failed/skipped/total), задачи по статусам
- `Backlog.tsx` — статус-кнопки, description, link, scheduled_date, убраны: minimal_time, use_pomodoro, allow_grouping, allow_multi_per_block, device_type, preferred_time, reminder_before

### Step 6: Calendar + версионные уведомления
- **Calendar.tsx** — события на временной шкале + задачи назначенные на день, drag задач на дни
- **DayColumn.tsx** — события на слотах + секция «Задачи на день» с быстрой сменой статуса
- **EventForm.tsx** — новая форма создания/редактирования событий (категория, время, напоминание, заметки)
- **BacklogPanel.tsx** — упрощён: статус-иконки, фильтры (назначенные/готовые), scheduled_date
- Удалён BlockForm.tsx (заменён на EventForm)
- **version_notify.py** — авто-рассылка changelog при деплое, ручная рассылка из админки
- **VersionNotification модель** — отслеживание отправленных уведомлений
- **admin.py** — кнопка «📢 Рассылка всем» в админ-панели
- Удалён controls.py (функциональность в settings.py)

### v1.2.0 ключевые файлы (все изменённые):
**Backend:**
- `backend/db/models.py` — Event, VersionNotification, обновлены Task, TaskBlock, User
- `backend/db/database.py` — 10+ миграций
- `backend/api/schemas.py` — EventCreate/Update/Response, обновлены Task*, User*, Block*
- `backend/api/routes/events.py` — НОВЫЙ
- `backend/api/routes/tasks.py` — status/scheduled_date фильтры
- `backend/api/routes/users.py` — pomodoro settings
- `backend/bot/handlers/settings.py` — ПЕРЕРАБОТАН (stop/pause/resume/admin через кнопки)
- `backend/bot/handlers/plan.py` — ПЕРЕРАБОТАН (навигация кнопками)
- `backend/bot/handlers/backlog.py` — НОВЫЙ
- `backend/bot/handlers/callbacks.py` — ПЕРЕРАБОТАН (помодоро flow)
- `backend/bot/handlers/admin.py` — broadcast кнопка
- `backend/bot/scheduler.py` — ПЕРЕРАБОТАН (помодоро-циклы)
- `backend/bot/reminders.py` — ПЕРЕРАБОТАН (помодоро + события)
- `backend/bot/version_notify.py` — НОВЫЙ
- `backend/bot/__init__.py` — обновлены роутеры и команды
- `backend/config.py` — 40+ SPAM_TEXTS, SPAM_TEXTS_EVENT, SPAM_TEXTS_EOD
- `backend/main.py` — version notify при старте

**Frontend:**
- `frontend/src/types/index.ts` — Event, обновлены все типы
- `frontend/src/api/client.ts` — Events CRUD
- `frontend/src/store/index.ts` — events state
- `frontend/src/components/Calendar/Calendar.tsx` — ПЕРЕРАБОТАН
- `frontend/src/components/Calendar/DayColumn.tsx` — ПЕРЕРАБОТАН
- `frontend/src/components/Calendar/EventForm.tsx` — НОВЫЙ
- `frontend/src/components/Calendar/BacklogPanel.tsx` — ПЕРЕРАБОТАН
- `frontend/src/components/Backlog/Backlog.tsx` — ПЕРЕРАБОТАН
- `frontend/src/components/Settings/Settings.tsx` — ПЕРЕРАБОТАН
- `frontend/src/components/Summary/Summary.tsx` — ПЕРЕРАБОТАН

**Удалены:**
- `backend/bot/handlers/controls.py`
- `frontend/src/components/Calendar/BlockForm.tsx`

---

## v1.6.1 (2026-04-02)

**Исправлено:**
- `backend/api/routes/users.py` — `productive_mode_enabled` теперь сохраняется в PATCH /me/settings (поле не передавалось в kwargs)
- `backend/api/routes/blocks.py` — удалены 6 мёртвых функций (`_calculate_multi_distribution` и др.) использовавших удалённые колонки БД (`allow_multi_per_block`, `preferred_time`, `device_type`)

**Новое:**
- `frontend/src/components/Backlog/Backlog.tsx` — статус-фильтр: toggle-кнопки с мультивыбором, «Готово» скрыто по умолчанию

**Рефакторинг:**
- `frontend/src/constants/timezones.ts` — вынесен дублирующийся `TIMEZONE_DATA` из TimezoneSelect и Settings
- `frontend/src/store/index.ts` — удалены мёртвые `blocks`/`loadBlocks`
- `frontend/src/types/index.ts` — удалён неиспользуемый тип `BlockWarning`

---

## Известные баги / TODO

- [ ] Task 8 (Duolingo Английский урок, preferred_time=11:00) не группируется с tasks 7,9,10 (preferred_time=11:30) — разные preferred_time (неактуально для v1.2.0 — preferred_time удалён)

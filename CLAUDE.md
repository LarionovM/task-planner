# Task Planner Bot — Промпт для Claude Code

## Название проекта
**Task Planner Bot** — личный Telegram-бот-планировщик задач с Web App интерфейсом.

---

## Контекст и цель

Создай полный проект Telegram-бота Task Planner Bot.

Бот работает в **режиме белого списка**: только пользователи из таблицы `allowed_users` в БД могут им пользоваться. Все остальные получают сообщение: _"Бот недоступен. Обратитесь к администратору."_

Первый пользователь в белом списке — **администратор** (is_admin=true). Он добавляется через `ADMIN_USER_ID` в `.env` при первом запуске. Остальных пользователей админ добавляет через admin-панель в боте.

Язык интерфейса: **русский** (без i18n, без заглушек под другие языки).

Везде в боте и Web App должны быть **понятные пояснения, подсказки и help-тексты** — бот должен быть self-explanatory для нового пользователя.

---

## Стек и инфраструктура

### Сервер (Ubuntu/Debian, 512 MB RAM)
- Python 3.11+
- **aiogram 3.x** — webhook-режим (`USE_POLLING=true` в `.env` для локальной разработки)
- **FastAPI** — backend API для Web App + webhook endpoint
- **SQLite + SQLAlchemy 2.0 async (aiosqlite)** — НЕ PostgreSQL, критично для экономии RAM
- **APScheduler (AsyncIOScheduler)** — напоминания
- **Nginx** — reverse proxy
- **Let's Encrypt (certbot)** — HTTPS (обязателен для Telegram Mini Apps и webhook)
- **systemd** — управление процессом (НЕ Docker)

### Web App (React фронтенд)
- React + TypeScript + Vite
- **Хостинг: Cloudflare Pages** (бесплатно, CDN, деплой через GitHub)
- API запросы к серверу (FastAPI) через HTTPS
- **Тёмная тема**, mobile-first UI
- Drag & drop: **@dnd-kit**
- Графики/статистика: **recharts**

---

## База данных (SQLite, SQLAlchemy 2.0 async)

```sql
-- Белый список пользователей
allowed_users:
  id, telegram_id (unique), username, first_name,
  is_admin (bool, default false),
  is_active (bool, default true),
  added_by (telegram_id админа),
  added_at

-- Настройки пользователя
users:
  telegram_id (FK → allowed_users),
  timezone (default 'Europe/Moscow'),
  quiet_start (time, default '23:00'),
  quiet_end (time, default '08:00'),
  day_end_time (time, default '23:50'),
  created_at

-- Категории (у каждого пользователя свои)
categories:
  id, name, emoji, color, user_id, sort_order

-- Расписание недели
weekly_schedule:
  id, user_id,
  day_of_week (0=Пн, 6=Вс),
  is_day_off (bool),
  active_from (time),
  active_to (time)
  -- Дефолт: Пн-Пт 09:00-18:00, Сб-Вс выходные

-- Цели по категориям на неделю
weekly_goals:
  id, user_id, category_id, target_hours

-- Бэклог задач
tasks:
  id, user_id, name, category_id,
  minimal_time_min (default 1),
  estimated_time_min,
  priority (high/medium/low, default medium),
  use_pomodoro (bool, default false),
  is_recurring (bool, default false),
  recur_days (JSON array [0..6]),
  deadline (date, nullable),
  tags (JSON array of strings),
  depends_on (JSON array of task_ids),
  reminder_before_min (int, default 5),
  allow_grouping (bool, default true),
  spam_enabled (bool, default true),  -- включён ли спам для этой задачи
  is_deleted (bool, default false),
  created_at

-- Блоки в календаре
task_blocks:
  id, user_id,
  task_ids (JSON array),
  block_name (nullable),
  day (date),
  start_time (time),

  -- Тип длительности блока (одно из трёх):
  duration_type (fixed | open | range),
  duration_min (int, nullable),       -- для fixed: фиксированная длительность
  min_duration_min (int, nullable),   -- для range: минимум
  max_duration_min (int, nullable),   -- для range и open: максимум / порог напоминания

  -- Фактическое время (для open и range блоков)
  actual_start_at (datetime, nullable),   -- момент получения уведомления о старте
  actual_end_at (datetime, nullable),     -- момент нажатия «Завершить»
  actual_duration_min (int, nullable),    -- вычисляется при завершении

  status (planned/active/done/skipped/failed, default planned),
  is_mixed (bool, default false),
  notes (nullable),
  created_at

-- Настройки спама
spam_config:
  id, user_id,
  initial_interval_sec (default 10),
  multiplier (default 1.5),
  max_interval_sec (default 600),
  enabled (bool, default true),
  -- Категории для которых спам включён (пусто = все)
  spam_category_ids (JSON array of category_ids, default [])
  -- Пустой массив означает "применять ко всем категориям"
  -- Если массив не пустой — спам только для указанных категорий
  -- Финальное решение = spam_config.enabled AND category в списке AND task.spam_enabled

-- Логи событий
logs:
  id, user_id, task_block_id (nullable),
  event_type (
    reminder_prep |       -- за N мин до старта
    reminder_start |      -- уведомление о старте
    block_skipped |       -- нажал Пропустить
    block_active |        -- блок запущен (фиксируется actual_start_at)
    block_finished_early | -- нажал Завершить досрочно
    block_done |          -- опросник: Выполнено
    block_partial |       -- опросник: Частично
    block_failed |        -- опросник: Не выполнено
    pomodoro_break |      -- начало pomodoro-перерыва
    pomodoro_resume |     -- конец pomodoro-перерыва
    spam_started |
    spam_stopped |
    max_time_reminder |   -- напоминание при превышении max_duration
    day_summary           -- итог дня
  ),
  payload (JSON),         -- причина, комментарий, фактическое время и т.д.
  created_at
```

---

## Команды бота

Зарегистрировать через `bot.set_my_commands()` с понятными описаниями.

| Команда | Описание | Доступ |
|---|---|---|
| `/start` | Приветствие + кнопка открыть планировщик | Все из whitelist |
| `/help` | Справка по командам | Все |
| `/stop` | Остановить напоминания | Все |
| `/pause <время>` | Пауза (30m, 2h, 1d, до 18:00) | Все |
| `/resume` | Возобновить напоминания | Все |
| `/settings` | Настройки: TZ, тихое время, спам | Все |
| `/stats` | Статистика за неделю | Все |
| `/admin` | Панель администратора | Только is_admin=true |

### /start:
1. Не в whitelist → "Бот недоступен. Обратитесь к администратору."
2. Первый запуск → приветствие с описанием возможностей + кнопка "Открыть планировщик"
3. Уже настроен → приветствие + кнопка + краткая сводка на сегодня

### /admin (только is_admin=true):
```
➕ Добавить пользователя — по Telegram ID
🗑 Удалить пользователя
🔇 Отключить/включить пользователя (is_active)
📊 Статистика пользователя — выбрать из списка
👥 Список всех пользователей
```

---

## Web App — структура

### Экран 0: Выбор часового пояса (только при первом открытии)
- Автоопределение: `Intl.DateTimeFormat().resolvedOptions().timeZone`
- Показать: _"Определили автоматически: **Europe/Belgrade** — верно?"_
- Кнопки: **[✅ Верно]** **[🔄 Выбрать другой]**
- При выборе другого → поиск по списку популярных TZ
- Сохранить на сервер сразу

> TZ также меняется в Настройках Web App и через `/settings`

### Экран 1: Категории
Дефолт при первом запуске: `Работа 💼, Спорт 🏋️, Обучение 📚, Личное ❤️, Отдых 😴, Хобби 🎨, Режим 🌙`

- CRUD: название + emoji + цвет
- При удалении категории с задачами → диалог: удалить задачи / переназначить
- Drag для сортировки

### Экран 2: Расписание + настройки
- 7 дней: чекбокс "Выходной" ИЛИ `active_from/active_to` (шаг 30 мин)
- **Дефолт: Пн-Пт 09:00–18:00, Сб-Вс выходные**
- Кнопка "Скопировать на другие дни"
- Тихое время (`quiet_start` – `quiet_end`)
- Время итога дня (`day_end_time`)
- Настройки спама: интервал, множитель, max интервал, вкл/выкл, **список категорий** для которых спам применяется

### Экран 3: Цели по категориям
Слайдер + число: целевое кол-во часов в неделю для каждой категории.

### Экран 4: Бэклог задач

Поля задачи:

| Поле | Тип | Подсказка в UI |
|---|---|---|
| Название | text | обязательное |
| Категория | select | обязательное |
| Приоритет | select 🔴🟡🟢 | default: средний |
| Дедлайн | date picker | опционально |
| Повторяемость | toggle + дни недели | — |
| Теги | multi-input | — |
| Зависит от | select задачи | опционально |
| Мин. время (мин) | number | "минимум для одной сессии" |
| Примерное время (мин) | number | "сколько займёт обычно" |
| Напомнить за (мин) | number | default 5, "для концерта/самолёта — больше" |
| Pomodoro 🍅 | checkbox | "Разбивать на 25+5 мин" |
| Разрешить группировку | checkbox | default true |
| Включить спам | checkbox | default true, "Бот будет настойчив если проигнорируешь" |

Список: фильтры по категории/приоритету/тегу/дедлайну, сортировка, inline редактирование/удаление.
При удалении задачи с блоками в календаре → диалог подтверждения.

### Экран 5: Календарь недели (drag & drop)

- 7 колонок (Пн–Вс), временная шкала по активным часам (30-мин слоты)
- Панель бэклога сбоку для drag

**Типы блоков и их отображение в календаре:**

| Тип | Отображение | Иконка |
|---|---|---|
| `fixed` | Занимает `duration_min` слотов | — |
| `open` | Занимает `estimated_time_min` слотов (условно) | 🔓 |
| `range` | Занимает `(min+max)/2` или `estimated_time_min` слотов | ↔️ |

При создании блока в календаре — выбор типа длительности:
- **Фиксированный** → ввести минуты
- **Открытый** → ввести max_duration_min (порог напоминания, опционально)
- **Диапазон** → ввести min и max

**Остальная функциональность:**
- Pomodoro: backend рассчитывает структуру 25+5, показывать 🍅 на блоке
- Смешанный блок: multi-select задач → "Создать блок" → тип + длительность
- Пересечение блоков: красная подсветка, предупреждение, не блокировать
- Зависимости: предупреждение при нарушении порядка
- Кнопка **"Автораспределить"**
- Кнопка **"Перенести невыполненное"** на следующую неделю

### Экран 6: Саммари
- Часы по категориям: план vs цель (бары)
- Для open/range блоков — estimated время в плане, фактическое в статистике
- Кол-во pomodoro-блоков, свободное время
- ⚠️ Перегрузка (>90%), пересечения, дедлайны этой недели
- Кнопка **"Сохранить и запустить напоминания"** → бот подтверждает "✅ План сохранён!"

### Настройки (из шапки Web App)
- Часовой пояс, тихое время, время итога дня, параметры спама

---

## Логика напоминаний

### ⚠️ Критично: восстановление scheduler при рестарте
При каждом старте: читать `task_blocks WHERE status='planned' AND day >= today` → перепланировать все jobs в APScheduler.

---

### Схема работы напоминаний по типам блоков

#### ФИКСИРОВАННЫЙ блок (`duration_type = fixed`)

```
[За reminder_before_min] → Уведомление подготовки
[Старт]                  → Уведомление старта + кнопка «Завершить досрочно»
[Конец по расписанию]    → Опросник завершения
[Игнор опросника > 2мин] → Спам (если разрешён)
```

#### ОТКРЫТЫЙ блок (`duration_type = open`)

```
[За reminder_before_min] → Уведомление подготовки
[Старт]                  → Уведомление старта + кнопка «Завершить»
                           фиксируется actual_start_at
[Нажал «Завершить»]      → фиксируется actual_end_at, actual_duration_min
                           → Опросник завершения
[Если max_duration_min]  → Через max_duration_min напомнить:
                           «Ты уже X мин, не забыл завершить?»
[Игнор опросника > 2мин] → Спам (если разрешён)
```

#### БЛОК С ДИАПАЗОНОМ (`duration_type = range`)

```
[За reminder_before_min] → Уведомление подготовки
[Старт]                  → Уведомление старта + кнопка «Завершить досрочно»
                           фиксируется actual_start_at
[Через min_duration_min] → «Минимальное время прошло. Можешь завершать.»
                           + кнопка «Завершить»
[Нажал «Завершить»]      → фиксируется actual_end_at, actual_duration_min
                           → Опросник завершения
[Через max_duration_min] → «Ты уже X мин, не забыл завершить?»
[Игнор опросника > 2мин] → Спам (если разрешён)
```

---

### Тексты уведомлений

**1. Подготовка (за `reminder_before_min` до старта):**
```
⏰ Через {N} мин: {название блока}
📁 {категории} | ⏱ {длительность или «открытый»} мин
Подготовься: вода, поза, фокус 🎯
{если смешанный: «Задачи: A, B, C»}
```

**2. Старт блока:**

Для `fixed`:
```
🚀 Начинается: {название} — {X} мин
{если pomodoro: «Первый 25-мин фокус 🍅»}
{если смешанный: список подзадач}
```
Кнопка: **[⏹ Завершить досрочно]**

Для `open`:
```
🚀 Начинается: {название}
⏱ Открытый блок — нажми «Завершить» когда закончишь
{если max_duration_min: «Напомню через {max} мин»}
```
Кнопка: **[✅ Завершить]**

Для `range`:
```
🚀 Начинается: {название}
⏱ {min}–{max} мин
```
Кнопка: **[⏹ Завершить досрочно]**
(через `min_duration_min` кнопка меняется на **[✅ Завершить]**)

**3. Уведомление при превышении max_duration (`open` и `range`):**
```
⏰ Ты уже {X} мин на задаче «{название}».
Не забыл завершить?
```
Кнопка: **[✅ Завершить]**

**4. Опросник по окончании блока** (для всех типов кроме `open` без нажатия):
```
🏁 Время вышло: {название}
Как прошло?
```
Кнопки: **[✅ Выполнено]** **[⚡ Частично]** **[❌ Не выполнено]**

- Если **Частично** или **Не выполнено** → кнопки причины:
  **[Не успел]** **[Отвлёкся]** **[Неактуально]** **[Другое]**
- Если **Другое** → `force_reply` для комментария
- Залогировать результат + причину

**5. Игнор опросника > 2 мин → экспоненциальный спам:**

Условие срабатывания спама (все три должны быть true):
- `spam_config.enabled = true`
- категория блока входит в `spam_category_ids` (или список пустой = все)
- `task.spam_enabled = true` для задач в блоке

Параметры из `spam_config`:
- `initial_interval_sec` (default 10)
- `multiplier` (default 1.5)
- `max_interval_sec` (default 600)

Тексты (циклически):
```python
SPAM_TEXTS = [
    "эй 👋", "ты где?", "спим? 😴", "просыпайся!",
    "задача ждёт...", "не игнорь 😤", "время уходит ⏳",
    "ты серьёзно?", "ладно... но это твой выбор",
    "ещё один шанс 🔔", "я всё ещё здесь 👀", "tick tock... ⏰",
]
```

Правила:
- Спам **не отправляется** в тихое время и вне рабочего времени
- `message_id` спам-сообщений хранить в памяти: `dict[user_id → list[message_id]]`
- Любое сообщение от пользователя → удалить ВСЕ спам-сообщения → повторить опросник

**6. Pomodoro (если `use_pomodoro=true`, только для `fixed` блоков):**

Через 25 мин после старта:
```
⏸ 25 мин фокуса — стоп!
Перерыв 5 мин: встань, пройдись, подыши 🌿
```
Через 5 мин:
```
🍅 Поехали! Следующие 25 мин фокуса.
```

**7. Итог дня (`day_end_time`, если не в тихое время — иначе перенести на `quiet_end`):**
```
📊 Итог дня — {дата}

✅ Выполнено: X блоков
⚡ Частично: Y блоков
❌ Провалено: Z блоков
⏭ Пропущено: W блоков

📁 По категориям:
  Работа 💼: 2ч 30мин (план: 3ч)
  Спорт 🏋️: 1ч (план: 1ч) ✅
  ...

⏱ Фактическое время открытых блоков: X мин
```
+ Кнопка web_app "📅 Редактировать план"

**8. Редактирование активного блока через Web App:**
`PATCH /blocks/{id}` при `status='active'` → бот спрашивает:
```
⚠️ Блок «{название}» сейчас активен.
Что сделать с напоминаниями?
```
Кнопки: **[🔄 Обновить]** **[🗑 Отменить напоминания]** **[❌ Не менять]**

---

## Таблица: тихое время и рабочие часы

| Тип события | Рабочее время | Тихое время | Вне рабочего |
|---|---|---|---|
| Подготовка, старт, завершение, pomodoro | ✅ | ✅ | ✅ |
| Опросник завершения | ✅ | ✅ | ✅ |
| Напоминание о превышении max_duration | ✅ | ✅ | ✅ |
| Итог дня | ✅ | ❌ → перенести на quiet_end | — |
| **Спам** | ✅ | ❌ | ❌ |

---

## Структура проекта

```
task-planner/
├── CLAUDE.md
├── README.md
├── .env.example
├── setup.sh
│
├── backend/
│   ├── main.py                  # FastAPI app + aiogram webhook
│   ├── config.py                # pydantic-settings из .env
│   ├── bot/
│   │   ├── handlers/
│   │   │   ├── start.py         # /start, /help
│   │   │   ├── controls.py      # /stop, /pause, /resume
│   │   │   ├── settings.py      # /settings, /stats
│   │   │   ├── admin.py         # /admin
│   │   │   └── callbacks.py     # inline-кнопки: завершить, опросник, спам
│   │   ├── scheduler.py         # APScheduler + восстановление при старте
│   │   ├── reminders.py         # все типы напоминаний + спам-машина
│   │   └── middlewares.py       # проверка whitelist
│   ├── api/
│   │   ├── routes/
│   │   │   ├── users.py
│   │   │   ├── categories.py
│   │   │   ├── tasks.py
│   │   │   ├── blocks.py        # CRUD + логика типов блоков
│   │   │   ├── schedule.py
│   │   │   └── stats.py         # включая фактическое время open/range блоков
│   │   ├── schemas.py           # Pydantic v2
│   │   └── deps.py              # auth по X-Telegram-User-Id
│   ├── db/
│   │   ├── database.py
│   │   ├── models.py
│   │   └── crud/
│   │       ├── users.py
│   │       ├── tasks.py
│   │       ├── blocks.py
│   │       └── admin.py
│   └── requirements.txt
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── api/
│       ├── components/
│       │   ├── TimezoneSelect/  # Экран 0
│       │   ├── Categories/      # Экран 1
│       │   ├── WeekSchedule/    # Экран 2
│       │   ├── Goals/           # Экран 3
│       │   ├── Backlog/         # Экран 4
│       │   ├── Calendar/        # Экран 5
│       │   │   ├── BlockTypes/  # Компоненты для fixed/open/range блоков
│       │   │   └── ...
│       │   ├── Summary/         # Экран 6
│       │   └── Settings/
│       ├── store/               # Zustand
│       ├── types/
│       └── styles/
│           ├── theme.css
│           └── globals.css
│
├── nginx/
│   └── task-planner.conf
└── systemd/
    └── task-planner.service
```

---

## Переменные окружения (.env)

```bash
BOT_TOKEN=             # Токен от @BotFather
ADMIN_USER_ID=         # Твой Telegram ID (узнать у @userinfobot)
WEBHOOK_URL=           # https://yourdomain.com/webhook
WEBHOOK_SECRET=        # Случайная строка для верификации

DATABASE_URL=sqlite+aiosqlite:///./data/task_planner.db

API_BASE_URL=          # https://yourdomain.com/api
FRONTEND_URL=          # https://your-project.pages.dev

DEFAULT_TIMEZONE=Europe/Moscow
USE_POLLING=false      # true для локальной разработки
DEBUG=false
```

---

## Корнер-кейсы для обязательной реализации

1. **Восстановление scheduler** — при старте читать `task_blocks WHERE status='planned' AND day >= today` → перепланировать jobs. Для `open` и `range` блоков со статусом `active` — восстановить только напоминание о max_duration если оно ещё не прошло.

2. **Спам только в рабочее время** — проверять `current_local_time` против `quiet_start/quiet_end` и `active_from/active_to` перед каждой отправкой.

3. **Тройная проверка спама** — `spam_config.enabled` AND категория в `spam_category_ids` (или список пуст) AND `task.spam_enabled`.

4. **Open блок при рестарте** — если сервер упал пока блок был активен (`status='active'`, `actual_end_at=null`) → при старте отправить пользователю: "Бот перезапустился. Блок «{название}» был активен — как он прошёл?" + опросник.

5. **Пересечение блоков** — API возвращает `warning`, не ошибку 400.

6. **Удаление задачи с блоками** — API возвращает список affected blocks, фронт показывает диалог.

7. **Редактирование активного блока** — при `status='active'` бот спрашивает что делать с напоминаниями.

8. **Soft delete задач** — `is_deleted=true`, хранить для истории логов.

9. **Whitelist middleware** — aiogram middleware + FastAPI dependency проверяют `allowed_users`.

10. **Первый запуск пользователя** — автосоздать дефолтные категории, расписание (Пн-Пт 09-18, Сб-Вс выходные), `spam_config`.

11. **Admin статистика других** — только если `requesting_user.is_admin=true`.

12. **Итог дня в тихое время** — перенести на `quiet_end` следующего утра.

13. **Зависимости задач** — предупреждение в UI при нарушении порядка, не блокировка.

14. **Фактическое время в статистике** — для `open` и `range` блоков показывать `actual_duration_min`, для `fixed` — `duration_min`. В итоге дня и в графиках использовать фактическое время там где оно есть.

15. **Кнопка «Завершить досрочно» в стартовом сообщении** — для `fixed` и `range` блоков. При нажатии: зафиксировать `actual_end_at` → сразу показать опросник завершения → отменить запланированный job окончания.

16. **range блок: кнопка меняется через min_duration** — до `min_duration_min` кнопка "⏹ Завершить досрочно", после — "✅ Завершить" (семантически разные: досрочно vs в рамках диапазона).

---

## Требования к коду

- Async везде (asyncio, async SQLAlchemy, async handlers)
- Type hints везде
- Pydantic v2 для схем FastAPI
- Логирование через `logging`, не `print`
- Все магические числа → константы в `config.py` или `.env`
- Комментарии на русском языке
- UX-тексты — понятные, не технические, с пояснениями

---

## Как использовать этот файл

Положи `CLAUDE.md` в корень `D:\ClaudeCodeProjects\task-planner\` и запусти Claude Code из этой папки.

**Первая фраза в Claude Code:**
```
Прочитай CLAUDE.md и составь пошаговый план разработки с чёткими
контрольными точками проверки для каждого этапа. На каждом этапе
должна быть возможность запустить и проверить то что уже работает,
прежде чем переходить к следующему.
```

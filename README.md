# Task Planner Bot

Telegram-бот-планировщик задач с Web App интерфейсом.

**Стек:** Python 3.11+ (FastAPI, aiogram 3.x, SQLAlchemy 2.0 async, APScheduler) + React/TypeScript/Vite

---

## Быстрый старт (локальная разработка)

```bash
# 1. Backend
cp .env.example .env
# Заполнить BOT_TOKEN и ADMIN_USER_ID в .env

python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

pip install -r backend/requirements.txt
uvicorn backend.main:app --reload

# 2. Frontend (в отдельном терминале)
cd frontend
npm install
npm run dev
# Откроется на http://localhost:5173
```

---

## Структура проекта

```
task-planner/
├── backend/                 # Python бэкенд
│   ├── main.py              # FastAPI + aiogram
│   ├── config.py            # Настройки из .env
│   ├── api/routes/           # REST API
│   ├── bot/handlers/         # Команды бота
│   ├── bot/scheduler.py      # APScheduler
│   ├── bot/reminders.py      # Напоминания
│   └── db/                   # SQLAlchemy модели + CRUD
├── frontend/                # React фронтенд
│   ├── src/components/       # Экраны Web App
│   └── dist/                 # Собранная статика
├── nginx/                   # Nginx конфиг
├── systemd/                 # Systemd service
├── setup.sh                 # Установочный скрипт
├── .env.example             # Шаблон переменных
└── CHANGELOG.md             # Лог изменений
```

---

## Возможности

- Белый список пользователей с системой запросов доступа
- Категории задач с emoji и цветами
- Бэклог задач: приоритеты, дедлайны, теги, зависимости, группы (эпики)
- Календарь недели с drag & drop
- 3 типа блоков: фиксированный, открытый, диапазон
- Pomodoro-таймер (25+5 мин)
- Умные напоминания: подготовка, старт, завершение, опросник
- Экспоненциальный спам при игнорировании
- Напоминания о пустых слотах в расписании
- Итог дня с категориями и статистикой
- Админ-панель: управление пользователями

"""Уведомления о новых версиях — автоматическая рассылка при деплое.

При каждом запуске бота:
1. Проверяет текущую версию (APP_VERSION)
2. Для каждого активного пользователя проверяет, получал ли он уведомление
3. Если нет — отправляет changelog и записывает в БД
"""

import logging
from datetime import datetime

from sqlalchemy import select

from backend.db.database import async_session
from backend.db.crud.users import get_all_active_users
from backend.db.models import VersionNotification

logger = logging.getLogger(__name__)

# === Текущая версия и changelog ===

APP_VERSION = "1.4.0"

# Changelog для каждой версии — отправляется пользователям
CHANGELOGS: dict[str, str] = {
    "1.4.0": (
        "🚀 *Task Planner v1.4.0*\n\n"
        "📊 *Аналитика (новый экран)*\n"
        "• Статистика за день / неделю / месяц\n"
        "• Графики: помодоро по дням (bar chart)\n"
        "• Распределение времени по категориям (pie chart)\n"
        "• Стрик, среднее помодоро в день, суммарный фокус\n"
        "• Дедлайны и задачи в периоде\n\n"
        "⚙️ *Настройки — по вкладкам*\n"
        "• Общее: расписание, рабочий день, часовой пояс\n"
        "• Бот: параметры спам-напоминаний\n"
        "• Таймер: настройки помодоро\n"
        "• Категории: CRUD + цели\n\n"
        "📅 *Календарь*\n"
        "• Задачи из «Задачи на день» можно перетащить на слот времени\n\n"
        "🐛 *Исправлено*\n"
        "• Создание задач через Web App\n"
        "• Кнопки помодоро в боте (был сбой)\n"
        "• Перерывы помодоро снова приходят\n"
        "• Ведущий ноль в числовых полях таймера\n"
    ),
    "1.3.3": (
        "🔧 *Task Planner v1.3.3*\n\n"
        "📅 *Календарь*\n"
        "• Задачи на день перенесены наверх — до временных слотов\n"
        "• Кнопка + для назначения задачи теперь заметная (синяя)\n"
    ),
    "1.3.2": (
        "🔧 *Task Planner v1.3.2*\n\n"
        "🎨 *Кнопка темы — в хедере*\n"
        "• Переключатель ☀️/🌙 теперь в верхней панели, не перекрывает кнопки\n\n"
        "🔍 *Панель сортировки*\n"
        "• Иконки увеличены и выделены фоном\n\n"
        "📅 *Планирование задач*\n"
        "• Кнопки «Сегодня» / «Завтра» при выборе даты\n"
        "• Кнопка + в календаре — назначить задачу на день без drag\n"
        "• Фильтр статусов — выпадающий список вместо кнопок\n\n"
        "🐛 *Исправлено*\n"
        "• Создание событий (созвонов) — ошибка 500"
    ),
    "1.3.1": (
        "🔧 *Task Planner v1.3.1*\n\n"
        "🎨 *Кнопка темы — в хедере*\n"
        "• Переключатель ☀️/🌙 теперь в верхней панели каждого экрана\n"
        "• Больше не перекрывает другие кнопки\n\n"
        "🔍 *Панель сортировки*\n"
        "• Иконки сортировки увеличены и хорошо видны\n"
        "• Панель выделена фоном и рамкой\n"
    ),
    "1.3.0": (
        "🚀 *Task Planner v1.3.0*\n\n"
        "🎨 *Тёмная / светлая тема*\n"
        "• Переключатель ☀️/🌙 на каждом экране\n"
        "• Выбор сохраняется между сессиями\n\n"
        "⚡ *Быстрая смена статуса*\n"
        "• Нажми на иконку статуса задачи чтобы переключить\n"
        "• Grooming → В работе → Готово (и обратно)\n\n"
        "📅 *Календарь*\n"
        "• Исправлены цвета дат и заголовков\n"
        "• Улучшен контраст кнопок сортировки\n\n"
        "🗑 *Удаление групп*\n"
        "• При удалении группы удаляются все задачи внутри\n"
        "• Подтверждение с количеством задач\n\n"
        "📅 *Кнопка Web App*\n"
        "• Планировщик теперь доступен из меню чата Telegram\n\n"
        "⚙️ *Прочее*\n"
        "• Раздел настроек: «Рабочий день» вместо «Начало и конец дня»\n"
        "• Пояснение множителя спама с примером"
    ),
    "1.2.0": (
        "🚀 *Task Planner v1.2.0*\n\n"
        "🍅 *Помодоро — центральная механика*\n"
        "• Автоматические циклы 25+5 мин весь рабочий день\n"
        "• Каждый 4-й помодоро — длинный перерыв 30 мин\n"
        "• В начале каждого помодоро — выбор задачи\n"
        "• Настройки помодоро в /settings и Web App\n\n"
        "📌 *События (созвоны, встречи)*\n"
        "• Отдельная сущность — не задача, не в статистике\n"
        "• Во время события помодоро молчит\n"
        "• Завершение только по кнопке в боте\n\n"
        "📋 *Статусы задач*\n"
        "• Grooming → В работе → Заблокировано → Готово\n"
        "• Смена статуса из /backlog и Web App\n"
        "• Фильтр по статусам\n\n"
        "📝 *Описание и ссылки*\n"
        "• У задач теперь есть описание и ссылка\n"
        "• Показываются при выборе задачи в помодоро\n\n"
        "😤 *Расширенный спам*\n"
        "• 40+ текстов с разными сценариями\n"
        "• Спам для незавершённых событий\n\n"
        "📊 *Итог дня*\n"
        "• Помодоро-статистика\n"
        "• Перенос незавершённых задач на след. рабочий день\n\n"
        "⚙️ *Прочее*\n"
        "• /settings — пауза, стоп, спам, админка (всё через кнопки)\n"
        "• /plan — навигация по дням\n"
        "• Убраны: тихое время, мин. время, группировка блоков"
    ),
}


async def notify_new_version(bot) -> int:
    """Рассылает changelog новой версии всем пользователям.

    Вызывается при старте бота. Возвращает количество отправленных уведомлений.
    """
    sent_count = 0
    changelog = CHANGELOGS.get(APP_VERSION)
    if not changelog:
        logger.info(f"Нет changelog для версии {APP_VERSION}")
        return 0

    async with async_session() as session:
        users = await get_all_active_users(session)

    for user in users:
        try:
            # Проверяем, получал ли уведомление
            async with async_session() as session:
                result = await session.execute(
                    select(VersionNotification).where(
                        VersionNotification.user_id == user.telegram_id,
                        VersionNotification.version == APP_VERSION,
                    )
                )
                already_sent = result.scalar_one_or_none()

            if already_sent:
                continue

            # Отправляем
            await bot.send_message(
                user.telegram_id,
                changelog,
                parse_mode="Markdown",
            )

            # Записываем в БД
            async with async_session() as session:
                notification = VersionNotification(
                    user_id=user.telegram_id,
                    version=APP_VERSION,
                )
                session.add(notification)
                await session.commit()

            sent_count += 1
            logger.info(f"Version notification sent to user={user.telegram_id}")

        except Exception as e:
            logger.error(f"Failed to notify user={user.telegram_id}: {e}")

    logger.info(f"Version {APP_VERSION} notifications: {sent_count} sent")
    return sent_count


async def send_custom_broadcast(bot, text: str, admin_id: int) -> int:
    """Отправка произвольного сообщения всем активным пользователям.

    Используется через админ-панель.
    """
    sent_count = 0

    async with async_session() as session:
        users = await get_all_active_users(session)

    for user in users:
        try:
            await bot.send_message(
                user.telegram_id,
                text,
                parse_mode="Markdown",
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to broadcast to user={user.telegram_id}: {e}")

    logger.info(f"Broadcast from admin={admin_id}: {sent_count} sent")
    return sent_count

#!/bin/bash
# ============================================================
# Task Planner Bot — Скрипт установки на VPS (Ubuntu/Debian)
# ============================================================
#
# Использование:
#   scp -r . user@yourserver:/tmp/task-planner
#   ssh user@yourserver
#   cd /tmp/task-planner
#   sudo bash setup.sh
#
# Что делает:
#   1. Устанавливает системные пакеты (Python 3.11+, nginx, certbot)
#   2. Создаёт пользователя taskplanner
#   3. Копирует проект в /opt/task-planner
#   4. Создаёт Python venv и устанавливает зависимости
#   5. Настраивает nginx (reverse proxy + SSL)
#   6. Настраивает systemd (автозапуск)
#   7. Генерирует .env с вашими данными
#   8. Запускает бота
# ============================================================

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Task Planner Bot — Установка       ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""

# Проверяем что запущен от root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Ошибка: запустите скрипт от root (sudo bash setup.sh)${NC}"
   exit 1
fi

# === 1. Собираем данные ===
echo -e "${YELLOW}=== Настройка ====${NC}"
echo ""

read -p "Введите ваш домен (например, planner.example.com): " DOMAIN
if [ -z "$DOMAIN" ]; then
    echo -e "${RED}Домен обязателен!${NC}"
    exit 1
fi

read -p "Введите BOT_TOKEN от @BotFather: " BOT_TOKEN
if [ -z "$BOT_TOKEN" ]; then
    echo -e "${RED}BOT_TOKEN обязателен!${NC}"
    exit 1
fi

read -p "Введите ваш Telegram ID (узнать у @userinfobot): " ADMIN_USER_ID
if [ -z "$ADMIN_USER_ID" ]; then
    echo -e "${RED}ADMIN_USER_ID обязателен!${NC}"
    exit 1
fi

read -p "URL фронтенда на Cloudflare Pages (например, https://task-planner.pages.dev): " FRONTEND_URL
if [ -z "$FRONTEND_URL" ]; then
    echo -e "${YELLOW}Фронтенд не указан, используем https://${DOMAIN}${NC}"
    FRONTEND_URL="https://${DOMAIN}"
fi

# Генерируем WEBHOOK_SECRET
WEBHOOK_SECRET=$(openssl rand -hex 32)
echo -e "${GREEN}WEBHOOK_SECRET сгенерирован автоматически${NC}"
echo ""

# === 2. Установка пакетов ===
echo -e "${YELLOW}=== Установка системных пакетов ===${NC}"

apt update -y
apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx curl

# Проверяем версию Python
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}Python: ${PYTHON_VERSION}${NC}"

# === 3. Создаём пользователя ===
echo -e "${YELLOW}=== Создание пользователя taskplanner ===${NC}"

if id "taskplanner" &>/dev/null; then
    echo -e "${GREEN}Пользователь taskplanner уже существует${NC}"
else
    useradd --system --shell /bin/false --home /opt/task-planner taskplanner
    echo -e "${GREEN}Пользователь taskplanner создан${NC}"
fi

# === 4. Копируем проект ===
echo -e "${YELLOW}=== Копирование проекта ===${NC}"

INSTALL_DIR="/opt/task-planner"
mkdir -p "$INSTALL_DIR"

# Копируем backend
cp -r backend "$INSTALL_DIR/"
cp -r nginx "$INSTALL_DIR/"
cp -r systemd "$INSTALL_DIR/"

# Создаём директорию для БД
mkdir -p "$INSTALL_DIR/data"

# === 5. Python venv + зависимости ===
echo -e "${YELLOW}=== Создание venv и установка зависимостей ===${NC}"

python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt"

echo -e "${GREEN}Зависимости установлены${NC}"

# === 6. Генерируем .env ===
echo -e "${YELLOW}=== Генерация .env ===${NC}"

cat > "$INSTALL_DIR/.env" << EOF
# === Telegram Bot ===
BOT_TOKEN=${BOT_TOKEN}
ADMIN_USER_ID=${ADMIN_USER_ID}
WEBHOOK_URL=https://${DOMAIN}/webhook
WEBHOOK_SECRET=${WEBHOOK_SECRET}

# === База данных ===
DATABASE_URL=sqlite+aiosqlite:///./data/task_planner.db

# === URLs ===
API_BASE_URL=https://${DOMAIN}/api
FRONTEND_URL=${FRONTEND_URL}

# === Настройки ===
DEFAULT_TIMEZONE=Europe/Moscow
USE_POLLING=false
DEBUG=false
EOF

echo -e "${GREEN}.env создан в ${INSTALL_DIR}/.env${NC}"

# === 7. Права доступа ===
chown -R taskplanner:taskplanner "$INSTALL_DIR"
chmod 600 "$INSTALL_DIR/.env"

# === 8. Nginx ===
echo -e "${YELLOW}=== Настройка Nginx ===${NC}"

# Подставляем домен в конфиг
sed "s/yourdomain.com/${DOMAIN}/g" "$INSTALL_DIR/nginx/task-planner.conf" \
    > /etc/nginx/sites-available/task-planner.conf

# Активируем сайт
ln -sf /etc/nginx/sites-available/task-planner.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default  # Убираем дефолтный сайт

# Создаём директорию для certbot challenge
mkdir -p /var/www/certbot

# Проверяем конфиг
nginx -t

# Перезагружаем nginx (без SSL пока)
# Нужен временный конфиг для получения сертификата
echo -e "${YELLOW}=== Получение SSL сертификата ===${NC}"

# Сначала перезапускаем nginx для HTTP (certbot challenge)
systemctl restart nginx

# Получаем сертификат
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "admin@${DOMAIN}" || {
    echo -e "${YELLOW}Certbot не смог получить сертификат автоматически.${NC}"
    echo -e "${YELLOW}Запустите вручную: sudo certbot --nginx -d ${DOMAIN}${NC}"
}

# Перезагружаем nginx с SSL
systemctl reload nginx
echo -e "${GREEN}Nginx настроен${NC}"

# === 9. Systemd ===
echo -e "${YELLOW}=== Настройка systemd ===${NC}"

cp "$INSTALL_DIR/systemd/task-planner.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable task-planner
systemctl start task-planner

echo -e "${GREEN}Сервис task-planner запущен${NC}"

# === 10. Проверка ===
echo ""
echo -e "${YELLOW}=== Проверка ===${NC}"

sleep 2  # Даём время на запуск

if systemctl is-active --quiet task-planner; then
    echo -e "${GREEN}✅ Сервис task-planner работает${NC}"
else
    echo -e "${RED}❌ Сервис не запустился. Проверьте: journalctl -u task-planner -n 50${NC}"
fi

# Проверяем API
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/health" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ API отвечает (health check OK)${NC}"
else
    echo -e "${YELLOW}⚠️  API пока не отвечает (код: ${HTTP_CODE}). Подождите пару секунд и проверьте:${NC}"
    echo -e "   curl https://${DOMAIN}/api/health"
fi

# === Итог ===
echo ""
echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Установка завершена! 🎉        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "🌐 API:       https://${DOMAIN}/api/health"
echo -e "🤖 Webhook:   https://${DOMAIN}/webhook"
echo -e "📂 Проект:    ${INSTALL_DIR}"
echo -e "📋 Логи:      journalctl -u task-planner -f"
echo -e "🔄 Рестарт:   sudo systemctl restart task-planner"
echo -e "📊 Статус:    sudo systemctl status task-planner"
echo ""
echo -e "${YELLOW}Следующий шаг: задеплоить фронтенд на Cloudflare Pages${NC}"
echo -e "  1. Запушить проект в GitHub"
echo -e "  2. Подключить репозиторий в Cloudflare Pages"
echo -e "  3. Build command: cd frontend && npm install && npm run build"
echo -e "  4. Build output: frontend/dist"
echo -e "  5. Env variable: VITE_API_URL=https://${DOMAIN}/api"
echo ""

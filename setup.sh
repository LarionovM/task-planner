#!/bin/bash
# ============================================================
# Task Planner Bot — Скрипт установки на VPS (Ubuntu/Debian)
# ============================================================
#
# Использование:
#   cd /opt/task-planner   (проект уже склонирован сюда)
#   sudo bash setup.sh
#
# Что делает:
#   1. Устанавливает системные пакеты (Python 3, nginx, certbot)
#   2. Создаёт пользователя taskplanner
#   3. Создаёт Python venv и устанавливает зависимости
#   4. Генерирует .env с вашими данными
#   5. Настраивает nginx (reverse proxy + SSL)
#   6. Настраивает systemd (автозапуск)
#   7. Запускает бота
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

# Проверяем что мы в правильной директории
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$APP_DIR/backend/requirements.txt" ]; then
    echo -e "${RED}Ошибка: запустите скрипт из корня проекта!${NC}"
    echo -e "  cd /opt/task-planner && sudo bash setup.sh"
    exit 1
fi

echo -e "Директория проекта: ${GREEN}${APP_DIR}${NC}"
echo ""

# === 1. Собираем данные ===
echo -e "${YELLOW}=== Настройка ===${NC}"
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

read -p "URL фронтенда (Enter = заполнить позже): " FRONTEND_URL

# Генерируем WEBHOOK_SECRET
WEBHOOK_SECRET=$(openssl rand -hex 32)
echo -e "${GREEN}WEBHOOK_SECRET сгенерирован автоматически${NC}"
echo ""

# === 2. Установка пакетов ===
echo -e "${YELLOW}=== Установка системных пакетов ===${NC}"

apt update -y
apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx curl

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}Python: ${PYTHON_VERSION}${NC}"

# === 3. Создаём пользователя ===
echo -e "${YELLOW}=== Создание пользователя taskplanner ===${NC}"

if id "taskplanner" &>/dev/null; then
    echo -e "${GREEN}Пользователь taskplanner уже существует${NC}"
else
    useradd --system --shell /bin/false --no-create-home taskplanner
    echo -e "${GREEN}Пользователь taskplanner создан${NC}"
fi

# === 4. Директория для БД ===
mkdir -p "$APP_DIR/data"

# === 5. Python venv + зависимости ===
echo -e "${YELLOW}=== Создание venv и установка зависимостей ===${NC}"

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt"

echo -e "${GREEN}Зависимости установлены${NC}"

# === 6. Генерируем .env ===
echo -e "${YELLOW}=== Генерация .env ===${NC}"

cat > "$APP_DIR/.env" << EOF
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

echo -e "${GREEN}.env создан${NC}"

# === 7. Права доступа ===
chown -R taskplanner:taskplanner "$APP_DIR/data"
chown taskplanner:taskplanner "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

# === 8. Nginx ===
echo -e "${YELLOW}=== Настройка Nginx ===${NC}"

# Подставляем домен в конфиг
sed "s/yourdomain.com/${DOMAIN}/g" "$APP_DIR/nginx/task-planner.conf" \
    > /etc/nginx/sites-available/task-planner.conf

# Активируем сайт
ln -sf /etc/nginx/sites-available/task-planner.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Создаём директорию для certbot challenge
mkdir -p /var/www/certbot

# Временный HTTP-only конфиг для certbot
cat > /etc/nginx/sites-available/task-planner-temp.conf << NGINXEOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 'Setting up...';
        add_header Content-Type text/plain;
    }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/task-planner-temp.conf /etc/nginx/sites-enabled/task-planner.conf
nginx -t && systemctl restart nginx

echo -e "${GREEN}Nginx запущен (HTTP)${NC}"

# === 9. SSL сертификат ===
echo -e "${YELLOW}=== Получение SSL сертификата ===${NC}"

certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect || {
    echo -e "${YELLOW}Certbot не смог получить сертификат автоматически.${NC}"
    echo -e "${YELLOW}Запустите вручную: sudo certbot --nginx -d ${DOMAIN}${NC}"
    echo -e "${YELLOW}Продолжаем без SSL...${NC}"
}

# Ставим полный конфиг
sed "s/yourdomain.com/${DOMAIN}/g" "$APP_DIR/nginx/task-planner.conf" \
    > /etc/nginx/sites-available/task-planner.conf
ln -sf /etc/nginx/sites-available/task-planner.conf /etc/nginx/sites-enabled/task-planner.conf
rm -f /etc/nginx/sites-available/task-planner-temp.conf

nginx -t && systemctl reload nginx
echo -e "${GREEN}Nginx с SSL настроен${NC}"

# === 10. Systemd ===
echo -e "${YELLOW}=== Настройка systemd ===${NC}"

cp "$APP_DIR/systemd/task-planner.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable task-planner
systemctl start task-planner

echo -e "${GREEN}Сервис task-planner запущен${NC}"

# === 11. Проверка ===
echo ""
echo -e "${YELLOW}=== Проверка ===${NC}"

sleep 2

if systemctl is-active --quiet task-planner; then
    echo -e "${GREEN}✅ Сервис task-planner работает${NC}"
else
    echo -e "${RED}❌ Сервис не запустился. Проверьте: journalctl -u task-planner -n 50${NC}"
fi

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/health" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ API отвечает (health check OK)${NC}"
else
    echo -e "${YELLOW}⚠️  API пока не отвечает (код: ${HTTP_CODE}). Подождите и проверьте:${NC}"
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
echo -e "📂 Проект:    ${APP_DIR}"
echo -e "📋 Логи:      journalctl -u task-planner -f"
echo -e "🔄 Рестарт:   sudo systemctl restart task-planner"
echo -e "📊 Статус:    sudo systemctl status task-planner"
echo ""
if [ -z "$FRONTEND_URL" ]; then
    echo -e "${YELLOW}Не забудь:${NC}"
    echo -e "  1. Задеплоить фронтенд на Cloudflare Pages"
    echo -e "  2. Вписать FRONTEND_URL в ${APP_DIR}/.env"
    echo -e "  3. sudo systemctl restart task-planner"
    echo ""
fi

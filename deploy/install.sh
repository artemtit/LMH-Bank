#!/usr/bin/env bash
#
# Установка LMH Bank на сервер (Debian/Ubuntu) как systemd-сервис.
#
# Запуск на сервере под root:
#   git clone https://github.com/artemtit/LMH-Bank.git
#   cd LMH-Bank
#   git checkout claude/telegram-banking-bot-3y56n8
#   BOT_TOKEN='ВАШ_ТОКЕН' bash deploy/install.sh
#
set -euo pipefail

APP_DIR="/opt/lmh-bank"
SERVICE_USER="lmhbank"
REPO_URL="https://github.com/artemtit/LMH-Bank.git"
BRANCH="${BRANCH:-claude/telegram-banking-bot-3y56n8}"

if [[ $EUID -ne 0 ]]; then
  echo "Запустите скрипт под root (или через sudo)." >&2
  exit 1
fi

if [[ -z "${BOT_TOKEN:-}" ]]; then
  echo "Не задан BOT_TOKEN. Пример: BOT_TOKEN='123:ABC' bash deploy/install.sh" >&2
  exit 1
fi

echo ">>> Устанавливаю системные пакеты..."
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git

echo ">>> Создаю системного пользователя '$SERVICE_USER'..."
if ! id "$SERVICE_USER" &>/dev/null; then
  useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

echo ">>> Разворачиваю код в $APP_DIR..."
if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" fetch origin "$BRANCH"
  git -C "$APP_DIR" checkout "$BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
  rm -rf "$APP_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

echo ">>> Создаю виртуальное окружение и ставлю зависимости..."
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo ">>> Пишу .env..."
cat > "$APP_DIR/.env" <<EOF
BOT_TOKEN=$BOT_TOKEN
DB_PATH=$APP_DIR/data/bank.db
ADMIN_IDS=${ADMIN_IDS:-}
EOF
chmod 600 "$APP_DIR/.env"

mkdir -p "$APP_DIR/data"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

echo ">>> Устанавливаю systemd-сервис..."
cp "$APP_DIR/deploy/lmh-bank.service" /etc/systemd/system/lmh-bank.service
systemctl daemon-reload
systemctl enable lmh-bank
systemctl restart lmh-bank

echo ">>> Готово. Статус:"
sleep 2
systemctl --no-pager status lmh-bank || true
echo
echo "Логи в реальном времени:  journalctl -u lmh-bank -f"

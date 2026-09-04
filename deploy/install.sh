#!/usr/bin/env bash
# ============================================================================
#  killspam-bot — Ubuntu serverga o'rnatish (doimiy ishlaydigan systemd service)
#  Ishlatish:  sudo bash install.sh
#  Idempotent: qayta-qayta ishga tushirsa bo'ladi.
# ============================================================================
set -euo pipefail

APP_USER="${SUDO_USER:-$(logname 2>/dev/null || echo root)}"
APP_DIR="/opt/killspam-bot"
REPO="https://github.com/anvarnarz/killspam-bot.git"
SERVICE="killspam-bot"
DB_NAME="spam_bot_db"
DB_USER="spam"
WEB_PORT="8090"

# --- .env uchun qiymatlar -----------------------------------------------------
# Sir repoda saqlanmaydi: chaqirganda env orqali bering, masalan
#   sudo BOT_TOKEN=123:ABC ADMIN_IDS=123456789 SERVER_IP=192.168.1.10 bash install.sh
# Bo'sh qolsa skript so'raydi. .env allaqachon mavjud bo'lsa — umuman kerak emas.
BOT_TOKEN="${BOT_TOKEN:-}"
ADMIN_IDS="${ADMIN_IDS:-}"
SERVER_IP="${SERVER_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
# gemini-2.5-flash yangi API kalitlar uchun yopilgan — 404 qaytaradi.
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.1-flash-lite}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mXATO: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "root sifatida ishga tushiring: sudo bash install.sh"

# ------------------------------------------------- 0. oldindan tekshiruv
# Bu skript NATIV o'rnatish uchun va har hostda ham ishlamaydi. Ikkala shartni
# oldindan tekshiramiz, aks holda xato o'rtada — pip resolve paytida yoki
# postgres ishga tushganda — chiqadi va sabab ko'rinmay qoladi.
preflight() {
    local fail=0 c ok_py="" v
    # 1) aiogram 3.13.0 => aiohttp<3.11 va pydantic<2.9; bularning Python 3.13+
    #    uchun wheel'i yo'q. Demak 3.11 yoki 3.12 shart.
    for c in python3.12 python3.11; do
        command -v "$c" >/dev/null 2>&1 && { ok_py="$c"; break; }
    done
    if [ -z "$ok_py" ]; then
        v="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo '?')"
        printf 'XATO: python3.11/python3.12 topilmadi (hostda: %s).\n' "$v" >&2
        printf '      aiogram 3.13.0 aiohttp<3.11 ni talab qiladi, u esa 3.13+ uchun wheel bermaydi.\n' >&2
        fail=1
    fi
    # 2) Nativ postgres 5432 ni egallaydi. Port band bo'lsa (masalan Docker'dagi
    #    boshqa loyihaning bazasi) Debian klasteri 5433 ga siljiydi va quyidagi
    #    DATABASE_URL jimgina BEGONA bazaga ishora qilib qoladi.
    if (ss -tln 2>/dev/null || netstat -tln 2>/dev/null) | grep -q ':5432[[:space:]]'; then
        printf 'XATO: 5432 porti allaqachon band — boshqa PostgreSQL ishlayapti.\n' >&2
        fail=1
    fi
    [ "$fail" -eq 0 ] || die "Bu host nativ o'rnatishga mos emas. docker-compose.yml dan foydalaning — deploy/README.md ga qarang."
}
preflight

# ---------------------------------------------------------------- 1. paketlar
log "Tizim paketlari"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl ca-certificates \
    python3 python3-venv python3-dev build-essential \
    postgresql postgresql-contrib libpq-dev

PY=python3
for c in python3.12 python3.11; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
PYVER="$($PY -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
log "Python: $PY ($PYVER)"
$PY -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' \
    || die "Python 3.11+ kerak, topilgani $PYVER"

# ---------------------------------------------------------------- 2. postgres
log "PostgreSQL sozlash"
systemctl enable --now postgresql

if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
    echo "  foydalanuvchi '$DB_USER' allaqachon bor — paroli saqlanadi"
    [ -f "$APP_DIR/.db_password" ] || die "$APP_DIR/.db_password yo'q. DB parolini qo'lda .env ga yozing yoki rolni o'chiring."
    DB_PASS="$(cat "$APP_DIR/.db_password")"
else
    DB_PASS="$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 24)"
    sudo -u postgres psql -qc "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS'"
    echo "  '$DB_USER' roli yaratildi"
fi

sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 \
    || sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
sudo -u postgres psql -qc "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER"
sudo -u postgres psql -qd "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER"

# ------------------------------------------------------------------- 3. kod
log "Kod: $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" fetch --quiet origin && git -C "$APP_DIR" reset --hard --quiet origin/master
else
    rm -rf "$APP_DIR"
    git clone --quiet "$REPO" "$APP_DIR"
fi
mkdir -p "$APP_DIR/logs"
printf '%s' "$DB_PASS" > "$APP_DIR/.db_password"
chmod 600 "$APP_DIR/.db_password"

# -------------------------------------------------------------------- 4. venv
log "Python venv + paketlar"
[ -d "$APP_DIR/.venv" ] || $PY -m venv "$APP_DIR/.venv"
VPY="$APP_DIR/.venv/bin/python"
$VPY -m pip install --quiet --upgrade pip

# Bosqichma-bosqich: hammasini birdan o'rnatsa pip resolver soatlab backtrack qiladi.
# psycopg2-binary 2.9.9 da Python 3.13 uchun wheel yo'q — yangi Python'da versiyani bo'shatamiz.
PSYCOPG="psycopg2-binary==2.9.9"
case "$PYVER" in 3.13|3.14) PSYCOPG="psycopg2-binary>=2.9.10" ;; esac

$VPY -m pip install --quiet --only-binary=:all: \
    "aiogram==3.13.0" "sqlalchemy==2.0.30" "$PSYCOPG" \
    "python-dotenv==1.0.1" "cryptography>=42.0.0" "aiohttp>=3.9"
$VPY -m pip install --quiet --only-binary=:all: "google-genai>=1.0.0" "nudenet>=3.4.2"

# --------------------------------------------------------------------- 5. .env
log ".env"
if [ -f "$APP_DIR/.env" ]; then
    echo "  .env allaqachon bor — tegilmaydi (o'zgartirish kerak bo'lsa qo'lda tahrirlang)"
else
    [ -n "$BOT_TOKEN" ] || read -r -p "  BOT_TOKEN (@BotFather): " BOT_TOKEN
    [ -n "$ADMIN_IDS" ] || read -r -p "  ADMIN_TELEGRAM_IDS (vergul bilan): " ADMIN_IDS
    [ -n "$BOT_TOKEN" ] || die "BOT_TOKEN bo'sh"
    [ -n "$ADMIN_IDS" ] || die "ADMIN_TELEGRAM_IDS bo'sh"
    FERNET="$($VPY -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
    cat > "$APP_DIR/.env" <<ENV
BOT_TOKEN=$BOT_TOKEN
DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
ADMIN_TELEGRAM_IDS=$ADMIN_IDS
KEY_ENCRYPTION_SECRET=$FERNET
BASE_URL=http://$SERVER_IP:$WEB_PORT
PORT=$WEB_PORT
GEMINI_MODEL=$GEMINI_MODEL
GEMINI_PRICE_IN=0.30
GEMINI_PRICE_OUT=2.50
REPORT_HOUR=9
MAX_GROUPS_PER_OWNER=20
ENV
    echo "  .env yaratildi (yangi Fernet kaliti bilan)"
fi
chmod 600 "$APP_DIR/.env"
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

# ------------------------------------------------------------------ 6. migratsiya
log "Baza migratsiyasi"
sudo -u "$APP_USER" "$VPY" "$APP_DIR/init_db.py"

# ------------------------------------------------------------------- 7. systemd
log "systemd service"
cat > "/etc/systemd/system/$SERVICE.service" <<UNIT
[Unit]
Description=killspam-bot — Telegram spam/fake account protection bot
Documentation=https://github.com/anvarnarz/killspam-bot
After=network-online.target postgresql.service
Wants=network-online.target
Requires=postgresql.service
# Telegram bilan aloqa uzilsa cheksiz qayta urinsin (start-limit bo'g'masin).
# systemd 229+ da bu direktiva [Unit] seksiyasiga tegishli.
StartLimitIntervalSec=0

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStartPre=$APP_DIR/.venv/bin/python $APP_DIR/init_db.py
ExecStart=$APP_DIR/.venv/bin/python -m spam_bot.main
Restart=always
RestartSec=10
StandardOutput=append:$APP_DIR/logs/bot.log
StandardError=append:$APP_DIR/logs/bot.log
Environment=PYTHONUNBUFFERED=1

# Xavfsizlik
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$APP_DIR

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"

# ------------------------------------------------------------------ 8. logrotate
cat > "/etc/logrotate.d/$SERVICE" <<ROT
$APP_DIR/logs/bot.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
ROT

# ----------------------------------------------------------------- 9. firewall
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    ufw allow "$WEB_PORT/tcp" >/dev/null 2>&1 || true
    log "ufw: $WEB_PORT/tcp ochildi"
fi

# ------------------------------------------------------------------ 10. natija
sleep 5
log "Holat"
systemctl --no-pager --lines=0 status "$SERVICE" || true
echo
if curl -fsS -m 5 "http://localhost:$WEB_PORT/health"; then
    echo
    log "TAYYOR ✅  http://$SERVER_IP:$WEB_PORT/health"
else
    echo
    printf '\033[1;31mWeb server javob bermadi. Log: journalctl -u %s -n 50\033[0m\n' "$SERVICE"
fi
cat <<TIPS

  Foydali buyruqlar:
    sudo systemctl status $SERVICE      # holat
    sudo systemctl restart $SERVICE     # qayta ishga tushirish
    sudo journalctl -u $SERVICE -f      # jonli log
    tail -f $APP_DIR/logs/bot.log       # fayl log

TIPS

#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="guardbot"
APP_DIR="/opt/guardbot"
SERVICE_FILE="/etc/systemd/system/guardbot.service"
REPO="${1:-}"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RESET='\033[0m'
info(){ echo -e "${CYAN}[*]${RESET} $*"; }
ok(){ echo -e "${GREEN}[✓]${RESET} $*"; }
warn(){ echo -e "${YELLOW}[!]${RESET} $*"; }
fail(){ echo -e "${RED}[x]${RESET} $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "این نصب‌کننده باید با sudo اجرا شود."
[[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || fail "آدرس مخزن را به شکل OWNER/REPO بده."
command -v apt-get >/dev/null 2>&1 || fail "این نصب‌کننده فعلاً برای Debian/Ubuntu طراحی شده است."

info "نصب پیش‌نیازهای لینوکس..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git curl ffmpeg python3 python3-venv python3-pip ca-certificates

PYTHON="$(command -v python3)"
PY_MINOR="$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
$PYTHON -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' \
  || fail "Python 3.11 یا جدیدتر لازم است؛ نسخه فعلی $PY_MINOR است."

if ! id "$APP_NAME" >/dev/null 2>&1; then
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_NAME"
fi

if [[ -d "$APP_DIR/.git" ]]; then
  info "مخزن قبلی پیدا شد؛ دریافت آخرین نسخه..."
  git -C "$APP_DIR" pull --ff-only
else
  [[ ! -e "$APP_DIR" ]] || fail "$APP_DIR از قبل وجود دارد و مخزن Git نیست؛ ابتدا آن را بررسی کن."
  info "دریافت مخزن https://github.com/$REPO ..."
  git clone --depth 1 "https://github.com/$REPO.git" "$APP_DIR"
fi

chown -R "$APP_NAME:$APP_NAME" "$APP_DIR"
info "ساخت محیط مجازی و نصب کتابخانه‌ها..."
runuser -u "$APP_NAME" -- bash -lc "cd '$APP_DIR' && python3 -m venv .venv && .venv/bin/python -m pip install --upgrade pip wheel && .venv/bin/pip install -r requirements.txt"

if [[ ! -f "$APP_DIR/.env" ]]; then
  info "بازکردن راه‌انداز رنگی؛ توکن و شناسه مالک را در آن وارد کن."
  runuser -u "$APP_NAME" -- bash -lc "cd '$APP_DIR' && .venv/bin/python cli.py"
else
  warn "فایل .env موجود است؛ برای حفظ تنظیمات قبلی، دوباره پرسیده نمی‌شود."
  read -r -p "تنظیمات را تغییر می‌دهی؟ [y/N] " CHANGE
  if [[ "$CHANGE" =~ ^[Yy]$ ]]; then
    runuser -u "$APP_NAME" -- bash -lc "cd '$APP_DIR' && .venv/bin/python cli.py --setup"
  fi
fi

[[ -s "$APP_DIR/.env" ]] || fail "فایل .env ساخته نشد؛ نصب متوقف شد."
chown "$APP_NAME:$APP_NAME" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=GuardBot Telegram Content Moderation Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_NAME
Group=$APP_NAME
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/bot.py
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=$APP_DIR

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable guardbot.service
systemctl restart guardbot.service
sleep 2
if systemctl is-active --quiet guardbot.service; then
  ok "GuardBot نصب و اجرا شد."
else
  warn "سرویس اجرا نشد؛ گزارش را با دستور زیر ببین: journalctl -u guardbot -n 100 --no-pager"
  systemctl status guardbot.service --no-pager || true
fi

echo
echo -e "${GREEN}دستورهای مدیریت:${RESET}"
echo "  وضعیت:       sudo systemctl status guardbot"
echo "  لاگ زنده:    sudo journalctl -u guardbot -f"
echo "  راه‌اندازی:  sudo systemctl restart guardbot"
echo "  تنظیم مجدد:  sudo -u guardbot $APP_DIR/.venv/bin/python $APP_DIR/cli.py --setup"
echo
echo "بعد از افزودن ربات به گروه/کانال، آن را ادمین کن و مجوز حذف پیام بده."

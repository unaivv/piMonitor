#!/usr/bin/env bash
set -euo pipefail

SERVICE_FILE="/etc/systemd/system/pimonitor.service"
WORK_DIR="$(cd "$(dirname "$0")" && pwd)"
CURRENT_USER="$(whoami)"

echo "=== piMonitor Installer ==="
echo "Directorio: $WORK_DIR"

# Virtualenv
python3 -m venv "$WORK_DIR/venv"
"$WORK_DIR/venv/bin/pip" install --upgrade pip -q
"$WORK_DIR/venv/bin/pip" install -r "$WORK_DIR/requirements.txt" -q

mkdir -p "$WORK_DIR/data"

# Reemplazamos el WorkingDirectory en el service file con la ruta real
sed "s|/home/pi/piMonitor|$WORK_DIR|g; s|User=pi|User=$CURRENT_USER|g" "$WORK_DIR/pimonitor.service" | sudo tee "$SERVICE_FILE" > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable pimonitor

echo ""
echo "✅ Instalación completa."
echo ""
echo "Próximos pasos:"
echo "  1. Editá config.yaml con tu bot token y chat ID de Telegram"
echo "  2. sudo systemctl start pimonitor"
echo "  3. Logs en vivo: journalctl -u pimonitor -f"

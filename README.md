# piMonitor

Resource monitor for Raspberry Pi with Telegram alerts and a web dashboard accessible via Cloudflare Tunnel.

![Dashboard](https://img.shields.io/badge/dashboard-live-3ecf8e?style=flat-square) ![Python](https://img.shields.io/badge/python-3.11+-6c8cff?style=flat-square) ![License](https://img.shields.io/badge/license-MIT-f5a623?style=flat-square)

## Features

- **Metrics** — CPU, RAM, temperature, and disk usage (multiple mounts supported)
- **Services** — live table of systemd services with status filter (running / stopped / failed)
- **Alerts** — Telegram notifications with cooldown and sustained-check anti-spike logic
- **Dashboard** — dark web UI with 24 h charts, auto-refresh every 30 s
- **History** — SQLite persistence with configurable retention (default 7 days)
- **Public access** — Cloudflare Tunnel, no open ports required

## Requirements

- Raspberry Pi running Raspberry Pi OS (Bookworm or later)
- Python 3.11+
- A Telegram bot token ([create one with @BotFather](https://t.me/botfather))
- A Cloudflare account with your domain managed by Cloudflare

## Installation

```bash
# Clone on your Pi
git clone https://github.com/unaivv/piMonitor.git
cd piMonitor

# Configure before installing
cp config.yaml config.yaml   # edit in place
nano config.yaml

# Install (creates venv, installs deps, registers systemd service)
bash install.sh
```

## Configuration

Edit `config.yaml`:

```yaml
check_interval: 60           # seconds between measurements
status_interval_minutes: 1440  # daily Telegram status summary (0 = off)
history_days: 7
web_port: 5000

telegram:
  bot_token: "YOUR_BOT_TOKEN"
  chat_id:   "YOUR_CHAT_ID"

thresholds:
  cpu_percent: 80
  ram_percent: 85
  disk_percent: 90
  temperature_celsius: 70

alert_cooldown_minutes: 30
sustained_checks: 3          # consecutive readings above threshold before alerting

disks:
  - path: /
    name: "System"
  - path: /mnt/externalDisk
    name: "External Disk"

# Leave empty to auto-detect non-system services
# watched_services:
#   - nginx
#   - cloudflared
#   - pimonitor
```

### Getting your Telegram chat ID

1. Start a chat with your bot and send `/start`
2. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Copy the `chat.id` value from the response

## Cloudflare Tunnel setup

```bash
# Install cloudflared (ARM64)
curl -L -o cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb

# Authenticate
cloudflared tunnel login

# Create tunnel and route DNS
cloudflared tunnel create pimonitor
cloudflared tunnel route dns pimonitor monitor.yourdomain.com

# Copy and edit the example config
cp cloudflared-config.yml ~/.cloudflared/config.yml
# Replace TUNNEL_ID with the ID returned above

# Install as a service
sudo cloudflared service install
sudo systemctl start cloudflared
```

If you already have a tunnel, just add a new ingress rule to your existing `/etc/cloudflared/config.yml`:

```yaml
- hostname: monitor.yourdomain.com
  service: http://localhost:5000
```

## Running

```bash
# Start
sudo systemctl start pimonitor

# Stop
sudo systemctl stop pimonitor

# Live logs
journalctl -u pimonitor -f

# Status
sudo systemctl status pimonitor
```

The service is enabled at boot automatically by the installer.

## Alert logic

An alert fires only when a metric stays **above its threshold for N consecutive checks** (default: 3). This avoids false positives from momentary spikes. After an alert is sent, it won't repeat for `alert_cooldown_minutes` (default: 30).

## Project structure

```
piMonitor/
├── monitor.py            # main loop + web server thread
├── config.yaml           # configuration
├── requirements.txt
├── install.sh            # setup script
├── pimonitor.service     # systemd unit
├── cloudflared-config.yml
├── src/
│   ├── collector.py      # metrics + services collection
│   ├── alerter.py        # Telegram
│   ├── storage.py        # SQLite
│   └── web.py            # Flask API + dashboard
└── templates/
    └── index.html        # web dashboard
```

## License

MIT

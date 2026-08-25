#!/usr/bin/env python3
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from src.alerter import TelegramAlerter
from src.collector import collect
from src.storage import MetricsStorage
from src import web

Path("data").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/monitor.log"),
    ],
)
logger = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


class Monitor:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.alerter = TelegramAlerter(
            config["telegram"]["bot_token"],
            config["telegram"]["chat_id"],
        )
        self.storage = MetricsStorage()
        self.thresholds: dict = config["thresholds"]
        self.cooldown = timedelta(minutes=config.get("alert_cooldown_minutes", 30))
        self.sustained: int = config.get("sustained_checks", 3)
        self._last_alert: dict[str, datetime] = {}
        self._hits: dict[str, int] = {}
        self._stop_event = threading.Event()
        self._running = True
        self.last_metrics: dict | None = None  # read by web API

    # ─── alert helpers ───────────────────────────────────────────────────────

    def _can_alert(self, key: str) -> bool:
        if self.storage.get_mute_until() is not None:
            return False
        last = self._last_alert.get(key)
        return last is None or (datetime.now() - last) > self.cooldown

    def _check(
        self, key: str, value: float | None, threshold: float, label: str, unit: str = "%"
    ) -> None:
        if value is None:
            return
        if value >= threshold:
            self._hits[key] = self._hits.get(key, 0) + 1
        else:
            self._hits[key] = 0
            return

        if self._hits[key] >= self.sustained and self._can_alert(key):
            msg = self.alerter.format_alert(label, value, threshold, unit)
            self.alerter.send(msg)
            self.storage.save_alert(key, value, threshold)
            self._last_alert[key] = datetime.now()
            logger.warning("Alert sent — %s: %s%s (threshold %s%s)", label, value, unit, threshold, unit)

    # ─── main loop ───────────────────────────────────────────────────────────

    def run(self) -> None:
        interval: int = self.config.get("check_interval", 60)
        status_minutes: int = self.config.get("status_interval_minutes", 0)
        status_every: int = (status_minutes * 60) // interval if status_minutes > 0 else 0
        disk_configs: list[dict] = self.config.get("disks", [{"path": "/", "name": "Sistema"}])
        history_days: int = self.config.get("history_days", 7)
        web_port: int = self.config.get("web_port", 5000)
        tick = 0

        signal.signal(signal.SIGTERM, self._handle_stop)
        signal.signal(signal.SIGINT, self._handle_stop)

        web.set_monitor(self)
        web.start(port=web_port)
        logger.info("Web dashboard at http://0.0.0.0:%d", web_port)

        logger.info("piMonitor started — interval %ss, thresholds: %s", interval, self.thresholds)
        self.alerter.send("✅ <b>piMonitor iniciado</b>\nMonitoreando cada %d segundos." % interval)

        while self._running:
            try:
                metrics = collect(disk_configs)
                self.last_metrics = metrics
                self.storage.save_metrics(metrics)

                self._check("cpu", metrics["cpu_percent"], self.thresholds.get("cpu_percent", 80), "CPU")
                self._check("ram", metrics["ram"]["percent"], self.thresholds.get("ram_percent", 85), "RAM")
                self._check(
                    "temp",
                    metrics["temperature"],
                    self.thresholds.get("temperature_celsius", 70),
                    "Temperatura",
                    "°C",
                )
                for name, disk in metrics["disks"].items():
                    if "error" not in disk:
                        self._check(
                            f"disk_{name}",
                            disk["percent"],
                            self.thresholds.get("disk_percent", 90),
                            f"Disco {name}",
                        )

                tick += 1
                if status_every > 0 and tick % status_every == 0:
                    self.alerter.send(self.alerter.format_status(metrics))

                self.storage.cleanup_old(days=history_days)

            except Exception:
                logger.exception("Unexpected error in monitoring loop")

            self._stop_event.wait(timeout=interval)

        self.storage.close()
        logger.info("piMonitor stopped")

    def _handle_stop(self, *_) -> None:
        logger.info("Shutdown signal received")
        self._running = False
        self._stop_event.set()


if __name__ == "__main__":
    cfg = load_config()
    Monitor(cfg).run()

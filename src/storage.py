import json
import sqlite3
from datetime import datetime
from pathlib import Path


class MetricsStorage:
    def __init__(self, db_path: str = "data/metrics.db") -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS metrics (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                cpu_percent REAL,
                ram_percent REAL,
                temperature REAL,
                disks_json  TEXT
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT  NOT NULL,
                metric    TEXT  NOT NULL,
                value     REAL,
                threshold REAL
            );
            CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(timestamp);
        """)
        self.conn.commit()

    def save_metrics(self, metrics: dict) -> None:
        self.conn.execute(
            "INSERT INTO metrics (timestamp, cpu_percent, ram_percent, temperature, disks_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(),
                metrics["cpu_percent"],
                metrics["ram"]["percent"],
                metrics["temperature"],
                json.dumps(metrics["disks"]),
            ),
        )
        self.conn.commit()

    def save_alert(self, metric: str, value: float, threshold: float) -> None:
        self.conn.execute(
            "INSERT INTO alerts (timestamp, metric, value, threshold) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(), metric, value, threshold),
        )
        self.conn.commit()

    def cleanup_old(self, days: int = 7) -> None:
        self.conn.execute(
            "DELETE FROM metrics WHERE timestamp < datetime('now', ?)",
            (f"-{days} days",),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

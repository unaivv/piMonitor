import json
import sqlite3
from datetime import datetime, timedelta
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
            CREATE TABLE IF NOT EXISTS mute (
                id          INTEGER PRIMARY KEY CHECK (id = 1),
                muted_until TEXT
            );
        """)
        self.conn.commit()

    def set_mute(self, minutes: int) -> str:
        """Mute alerts for `minutes` from now. Returns the muted-until ISO timestamp."""
        muted_until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        self.conn.execute(
            "INSERT INTO mute (id, muted_until) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET muted_until = excluded.muted_until",
            (muted_until,),
        )
        self.conn.commit()
        return muted_until

    def get_mute_until(self) -> datetime | None:
        """Current muted-until datetime, or None if not muted / mute has expired."""
        row = self.conn.execute("SELECT muted_until FROM mute WHERE id = 1").fetchone()
        if row is None or row[0] is None:
            return None
        muted_until = datetime.fromisoformat(row[0])
        if muted_until <= datetime.now():
            return None
        return muted_until

    def clear_mute(self) -> None:
        self.conn.execute(
            "INSERT INTO mute (id, muted_until) VALUES (1, NULL) "
            "ON CONFLICT(id) DO UPDATE SET muted_until = NULL"
        )
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

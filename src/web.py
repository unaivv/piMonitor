import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template

from src.collector import get_services

app = Flask(__name__, template_folder="../templates")
app.jinja_env.auto_reload = True

# Shared reference injected by monitor.py at startup
_monitor_ref = None


def set_monitor(monitor) -> None:
    global _monitor_ref
    _monitor_ref = monitor


def _db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect("data/metrics.db")
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def status():
    if _monitor_ref is None:
        return jsonify({"error": "monitor not ready"}), 503
    metrics = _monitor_ref.last_metrics
    if metrics is None:
        return jsonify({"error": "no data yet"}), 503
    return jsonify(metrics)


@app.route("/api/history")
def history():
    hours = 24
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    conn = _db_conn()
    rows = conn.execute(
        "SELECT timestamp, cpu_percent, ram_percent, temperature, disks_json "
        "FROM metrics WHERE timestamp >= ? ORDER BY timestamp ASC",
        (since,),
    ).fetchall()
    conn.close()
    return jsonify([
        {
            "ts": r["timestamp"],
            "cpu": r["cpu_percent"],
            "ram": r["ram_percent"],
            "temp": r["temperature"],
            "disks": json.loads(r["disks_json"]) if r["disks_json"] else {},
        }
        for r in rows
    ])


@app.route("/api/services")
def services():
    watched = None
    if _monitor_ref is not None:
        watched = _monitor_ref.config.get("watched_services") or None
    return jsonify(get_services(watched))


@app.route("/api/alerts")
def alerts():
    conn = _db_conn()
    rows = conn.execute(
        "SELECT timestamp, metric, value, threshold FROM alerts ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def start(host: str = "0.0.0.0", port: int = 5000) -> None:
    thread = threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    thread.start()

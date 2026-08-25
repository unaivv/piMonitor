import functools
import hashlib
import hmac
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qsl

from flask import (Flask, jsonify, redirect, render_template,
                   request, session, url_for)

from src.collector import get_services

app = Flask(__name__, template_folder="../templates")
app.jinja_env.auto_reload = True

_monitor_ref = None


def set_monitor(monitor) -> None:
    global _monitor_ref
    _monitor_ref = monitor
    # Derive a stable secret key from credentials so sessions survive restarts
    seed = (
        monitor.config.get("auth", {}).get("password", "pimonitor") +
        monitor.config.get("telegram", {}).get("bot_token", "")
    )
    app.secret_key = hashlib.sha256(seed.encode()).digest()
    app.permanent_session_lifetime = timedelta(days=30)


def _auth_enabled() -> tuple[str, str] | None:
    if _monitor_ref is None:
        return None
    cfg = _monitor_ref.config.get("auth", {})
    u, p = cfg.get("username", ""), cfg.get("password", "")
    return (u, p) if u and p else None


def _verify_telegram(init_data: str) -> bool:
    """Verify Telegram WebApp initData HMAC signature."""
    try:
        bot_token = _monitor_ref.config.get("telegram", {}).get("bot_token", "")
        if not bot_token or not init_data:
            return False
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", "")
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_hash, received_hash):
            return False
        # Reject tokens older than 24 hours
        auth_date = int(parsed.get("auth_date", 0))
        return (time.time() - auth_date) < 86400
    except Exception:
        return False


def _require_auth(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if _auth_enabled() and not session.get("authenticated"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


@app.route("/api/telegram-auth", methods=["POST"])
def telegram_auth():
    init_data = (request.get_json() or {}).get("init_data", "")
    if _verify_telegram(init_data):
        session.permanent = True
        session["authenticated"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 403


@app.route("/login", methods=["GET", "POST"])
def login():
    creds = _auth_enabled()
    if not creds:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        if (request.form.get("username") == creds[0] and
                request.form.get("password") == creds[1]):
            session.permanent = True
            session["authenticated"] = True
            return redirect(request.args.get("next") or url_for("index"))
        error = "Usuario o contraseña incorrectos."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect("data/metrics.db")
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
@_require_auth
def index():
    return render_template("index.html")


@app.route("/api/status")
@_require_auth
def status():
    if _monitor_ref is None:
        return jsonify({"error": "monitor not ready"}), 503
    metrics = _monitor_ref.last_metrics
    if metrics is None:
        return jsonify({"error": "no data yet"}), 503
    return jsonify(metrics)


@app.route("/api/history")
@_require_auth
def history():
    since = (datetime.now() - timedelta(hours=24)).isoformat()
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
@_require_auth
def services():
    watched = _monitor_ref.config.get("watched_services") or None if _monitor_ref else None
    return jsonify(get_services(watched))


@app.route("/api/alerts")
@_require_auth
def alerts():
    conn = _db_conn()
    rows = conn.execute(
        "SELECT timestamp, metric, value, threshold FROM alerts ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/mute", methods=["GET"])
@_require_auth
def get_mute():
    if _monitor_ref is None:
        return jsonify({"error": "monitor not ready"}), 503
    muted_until = _monitor_ref.storage.get_mute_until()
    return jsonify({
        "muted": muted_until is not None,
        "until": muted_until.isoformat() if muted_until else None,
    })


@app.route("/api/mute", methods=["POST"])
@_require_auth
def post_mute():
    if _monitor_ref is None:
        return jsonify({"error": "monitor not ready"}), 503
    body = request.get_json(silent=True) or {}
    try:
        minutes = int(body.get("minutes"))
    except (TypeError, ValueError):
        return jsonify({"error": "minutes must be an integer"}), 400
    if minutes <= 0:
        return jsonify({"error": "minutes must be positive"}), 400
    muted_until = _monitor_ref.storage.set_mute(minutes)
    return jsonify({"muted": True, "until": muted_until})


@app.route("/api/mute/clear", methods=["POST"])
@_require_auth
def clear_mute():
    if _monitor_ref is None:
        return jsonify({"error": "monitor not ready"}), 503
    _monitor_ref.storage.clear_mute()
    return jsonify({"muted": False, "until": None})


def start(host: str = "0.0.0.0", port: int = 5000) -> None:
    thread = threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    thread.start()

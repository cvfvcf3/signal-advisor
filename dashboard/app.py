"""
dashboard/app.py
-----------------
Read-only Flask API + web UI. No control endpoints that change bot
behavior in a risky way -- this system doesn't trade, so there is nothing
dangerous to gate behind an admin token. The token is kept only for the
config-reload endpoint, to stop random visitors from tweaking thresholds.
"""

import os
import sys
import functools

from flask import Flask, jsonify, request, render_template

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = Flask(__name__)

advisor = None
journal = None
config_data = None


def require_admin_token(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        expected = os.getenv("DASHBOARD_ADMIN_TOKEN", "")
        provided = request.headers.get("X-Admin-Token", "")
        if not expected or provided != expected:
            return jsonify({"error": "Unauthorized. Set X-Admin-Token header."}), 401
        return fn(*args, **kwargs)
    return wrapper


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/current_signal")
def api_current_signal():
    if not advisor.last_reading:
        return jsonify({"action": "WAIT", "confidence": 0, "note": "No reading yet -- first tick still in progress."})
    return jsonify(advisor.last_reading)


@app.route("/api/signals")
def api_signals():
    limit = int(request.args.get("limit", 100))
    return jsonify(journal.get_recent_signals(advisor.symbol, limit=limit))


@app.route("/api/accuracy")
def api_accuracy():
    return jsonify(journal.get_accuracy_stats(advisor.symbol))


@app.route("/api/logs")
def api_logs():
    return jsonify(journal.get_recent_logs(limit=150))


@app.route("/api/candles")
def api_candles():
    from src.indicators import compute_all
    import pandas as pd
    raw = advisor.exchange.fetch_ohlcv(advisor.symbol, advisor.timeframe, 150)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    data = compute_all(df, config_data["indicators"])
    return jsonify(data.fillna(0).to_dict(orient="records"))


@app.route("/api/config")
def api_config():
    return jsonify(config_data)


@app.route("/api/config", methods=["POST"])
@require_admin_token
def api_update_config():
    updates = request.json or {}
    for section in ("scoring", "journal", "orderbook", "market_structure"):
        if section in updates and isinstance(updates[section], dict):
            if section == "scoring" and "weights" in updates[section]:
                config_data["scoring"]["weights"].update(updates[section]["weights"])
                updates[section] = {k: v for k, v in updates[section].items() if k != "weights"}
            config_data[section].update(updates[section])
    journal.log("Configuration updated via dashboard.", "info")
    return jsonify({"ok": True, "config": config_data})

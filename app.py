# -*- coding: utf-8 -*-
"""
Flask-сайт мониторинга завышенных цен на СЗПТ в госзакупках Актобе.
"""

import os
import json
import threading
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request

from config import REFERENCE_PRICES, THRESHOLD_PERCENT
from scraper import run_monitor

app = Flask(__name__)

# Простое хранилище результатов в памяти
CACHE = {
    "results": [],
    "last_update": None,
    "is_running": False,
    "log": [],
}


def background_scan(products=None):
    """Запускает скан в фоне."""
    CACHE["is_running"] = True
    CACHE["log"] = ["Сканирование запущено..."]
    try:
        results = run_monitor(products)
        CACHE["results"] = results
        CACHE["last_update"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        CACHE["log"].append(f"Готово. Найдено подозрительных лотов: {len(results)}")
    except Exception as e:
        CACHE["log"].append(f"Ошибка: {str(e)}")
    finally:
        CACHE["is_running"] = False


@app.route("/")
def index():
    return render_template(
        "index.html",
        products=REFERENCE_PRICES,
        threshold=THRESHOLD_PERCENT,
        results=CACHE["results"],
        last_update=CACHE["last_update"],
        is_running=CACHE["is_running"],
    )


@app.route("/api/scan", methods=["POST"])
def api_scan():
    if CACHE["is_running"]:
        return jsonify({"ok": False, "msg": "Сканирование уже идёт"})

    data = request.get_json(silent=True) or {}
    products = data.get("products")  # список или None

    thread = threading.Thread(target=background_scan, args=(products,), daemon=True)
    thread.start()

    return jsonify({"ok": True, "msg": "Сканирование запущено"})


@app.route("/api/status")
def api_status():
    return jsonify({
        "is_running": CACHE["is_running"],
        "last_update": CACHE["last_update"],
        "count": len(CACHE["results"]),
        "log": CACHE["log"][-8:],
        "results": CACHE["results"],
    })


@app.route("/api/results")
def api_results():
    return jsonify({
        "results": CACHE["results"],
        "last_update": CACHE["last_update"],
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

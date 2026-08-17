# -*- coding: utf-8 -*-
"""
Flask-сайт мониторинга завышенных цен на СЗПТ в госзакупках Актобе.
"""

import os
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request

from config import REFERENCE_PRICES, THRESHOLD_PERCENT
from scraper import run_monitor

app = Flask(__name__)

CACHE = {
    "results": [],
    "last_update": None,
    "is_running": False,
    "log": [],
    "threshold": THRESHOLD_PERCENT,
}


def background_scan(products=None, threshold=None):
    """Запускает скан в фоне."""
    CACHE["is_running"] = True
    CACHE["log"] = ["Сканирование запущено..."]
    try:
        thr = threshold if threshold is not None else CACHE.get("threshold", THRESHOLD_PERCENT)
        CACHE["threshold"] = thr
        results = run_monitor(products, threshold=thr)
        CACHE["results"] = results
        CACHE["last_update"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        CACHE["log"].append(f"Готово. Найдено подозрительных лотов: {len(results)} (порог +{thr}%)")
    except Exception as e:
        CACHE["log"].append(f"Ошибка: {str(e)}")
    finally:
        CACHE["is_running"] = False


@app.route("/")
def index():
    return render_template(
        "index.html",
        products=REFERENCE_PRICES,
        threshold=CACHE.get("threshold", THRESHOLD_PERCENT),
        results=CACHE["results"],
        last_update=CACHE["last_update"],
        is_running=CACHE["is_running"],
    )


@app.route("/api/scan", methods=["POST"])
def api_scan():
    if CACHE["is_running"]:
        return jsonify({"ok": False, "msg": "Сканирование уже идёт"})

    data = request.get_json(silent=True) or {}
    products = data.get("products")
    threshold = data.get("threshold")

    try:
        if threshold is not None:
            threshold = float(threshold)
            if threshold < 0:
                threshold = 0
            if threshold > 500:
                threshold = 500
        else:
            threshold = CACHE.get("threshold", THRESHOLD_PERCENT)
    except (TypeError, ValueError):
        threshold = CACHE.get("threshold", THRESHOLD_PERCENT)

    thread = threading.Thread(
        target=background_scan,
        args=(products, threshold),
        daemon=True
    )
    thread.start()

    return jsonify({"ok": True, "msg": f"Сканирование запущено (порог +{threshold}%)"})


@app.route("/api/status")
def api_status():
    return jsonify({
        "is_running": CACHE["is_running"],
        "last_update": CACHE["last_update"],
        "count": len(CACHE["results"]),
        "log": CACHE["log"][-8:],
        "results": CACHE["results"],
        "threshold": CACHE.get("threshold", THRESHOLD_PERCENT),
    })


@app.route("/api/results")
def api_results():
    return jsonify({
        "results": CACHE["results"],
        "last_update": CACHE["last_update"],
        "threshold": CACHE.get("threshold", THRESHOLD_PERCENT),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

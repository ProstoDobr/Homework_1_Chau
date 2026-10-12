"""
Простое веб-приложение для домашнего задания №1.

Функциональность (специально максимально простая — важно не ЧТО делает
приложение, а то, что весь пайплайн вокруг него работает):
  - список заметок с возможностью добавить / отредактировать / удалить
    (т.е. приложение "редактируется" через интерфейс, а не только запускается)
  - GET  /            — HTML-интерфейс (можно тыкать мышкой)
  - GET  /health      — health check для docker/compose/CI
  - GET  /metrics     — метрики в формате Prometheus:
        * потребляемые ресурсы контейнера/процесса (CPU, память)
        * доступные ресурсы хоста (сколько всего памяти/CPU)
        * посещений всего и посещений за последний час
"""

import os
import time
import sqlite3
import shutil
from collections import deque
from datetime import datetime
from flask import Flask, request, redirect, url_for, render_template, jsonify

APP_START_TIME = time.time()
DB_PATH = os.environ.get("DB_PATH", "/data/notes.db")

app = Flask(__name__)

# ---- метрика "посещений в час" -------------------------------------------
# храним временные метки запросов за последние 24 часа (этого достаточно,
# чтобы посчитать "посещений за последний час"); для настоящего продакшена
# это, конечно, вынесли бы в Prometheus Counter + rate(), но для домашки
# считаем сами, чтобы не тянуть лишние зависимости.
_visits_total = 0
_visit_timestamps = deque()


@app.before_request
def _track_visit():
    global _visits_total
    if request.path == "/metrics":
        return  # не считаем обращения самого мониторинга как "посещения"
    _visits_total += 1
    now = time.time()
    _visit_timestamps.append(now)
    while _visit_timestamps and now - _visit_timestamps[0] > 24 * 3600:
        _visit_timestamps.popleft()


def _visits_last_hour():
    now = time.time()
    return sum(1 for t in _visit_timestamps if now - t <= 3600)


# ---- база данных (простое хранилище заметок) ------------------------------
def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notes ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "title TEXT NOT NULL, "
        "body TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)"
    )
    return conn


@app.route("/")
def index():
    conn = get_db()
    notes = conn.execute("SELECT * FROM notes ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("index.html", notes=notes)


@app.route("/notes/new", methods=["POST"])
def create_note():
    title = request.form.get("title", "").strip() or "Без названия"
    body = request.form.get("body", "").strip()
    conn = get_db()
    conn.execute(
        "INSERT INTO notes (title, body, updated_at) VALUES (?, ?, ?)",
        (title, body, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/notes/<int:note_id>/edit", methods=["POST"])
def edit_note(note_id):
    title = request.form.get("title", "").strip() or "Без названия"
    body = request.form.get("body", "").strip()
    conn = get_db()
    conn.execute(
        "UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?",
        (title, body, datetime.utcnow().isoformat(), note_id),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/notes/<int:note_id>/delete", methods=["POST"])
def delete_note(note_id):
    conn = get_db()
    conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


# ---- health check -----------------------------------------------------
@app.route("/health")
def health():
    try:
        conn = get_db()
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False
    status = "ok" if db_ok else "degraded"
    code = 200 if db_ok else 503
    return jsonify(
        status=status,
        uptime_seconds=round(time.time() - APP_START_TIME, 1),
        db_ok=db_ok,
    ), code


# ---- метрики (ресурсы + посещения) ------------------------------------
def _read_proc_status_mem_bytes():
    """RSS текущего процесса в байтах, читаем из /proc — без внешних либ."""
    try:
        with open(f"/proc/{os.getpid()}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return kb * 1024
    except Exception:
        pass
    return 0


def _cpu_count():
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


def _load_avg():
    try:
        return os.getloadavg()
    except Exception:
        return (0.0, 0.0, 0.0)


def _mem_available_total():
    """Доступная и общая память ХОСТА/контейнера из /proc/meminfo."""
    total = available = 0
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    available = int(line.split()[1]) * 1024
    except Exception:
        pass
    return total, available


def _disk_usage():
    try:
        usage = shutil.disk_usage("/")
        return usage.total, usage.used, usage.free
    except Exception:
        return 0, 0, 0


@app.route("/metrics")
def metrics():
    load1, load5, load15 = _load_avg()
    mem_total, mem_available = _mem_available_total()
    disk_total, disk_used, disk_free = _disk_usage()
    process_rss = _read_proc_status_mem_bytes()

    lines = [
        "# HELP app_uptime_seconds Время работы приложения в секундах",
        "# TYPE app_uptime_seconds gauge",
        f"app_uptime_seconds {time.time() - APP_START_TIME:.1f}",

        "# HELP app_visits_total Общее количество посещений с момента старта",
        "# TYPE app_visits_total counter",
        f"app_visits_total {_visits_total}",

        "# HELP app_visits_last_hour Количество посещений за последний час",
        "# TYPE app_visits_last_hour gauge",
        f"app_visits_last_hour {_visits_last_hour()}",

        "# HELP process_resident_memory_bytes Память (RSS), потребляемая процессом приложения",
        "# TYPE process_resident_memory_bytes gauge",
        f"process_resident_memory_bytes {process_rss}",

        "# HELP system_cpu_count Количество доступных ядер CPU",
        "# TYPE system_cpu_count gauge",
        f"system_cpu_count {_cpu_count()}",

        "# HELP system_load1 Средняя загрузка системы за 1 минуту",
        "# TYPE system_load1 gauge",
        f"system_load1 {load1:.2f}",

        "# HELP system_memory_total_bytes Всего памяти доступно на хосте/в контейнере",
        "# TYPE system_memory_total_bytes gauge",
        f"system_memory_total_bytes {mem_total}",

        "# HELP system_memory_available_bytes Свободной (доступной) памяти сейчас",
        "# TYPE system_memory_available_bytes gauge",
        f"system_memory_available_bytes {mem_available}",

        "# HELP system_disk_total_bytes Всего места на диске",
        "# TYPE system_disk_total_bytes gauge",
        f"system_disk_total_bytes {disk_total}",

        "# HELP system_disk_free_bytes Свободно места на диске",
        "# TYPE system_disk_free_bytes gauge",
        f"system_disk_free_bytes {disk_free}",
    ]
    return "\n".join(lines) + "\n", 200, {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

"""Учебное веб-приложение «Заметки» (Flask + SQLite).

Назначение — дать что-то, что можно потыкать и отредактировать, и
показать вокруг него рабочий пайплайн: сборка, контейнер, мониторинг.

Страницы:
  /         интерфейс: добавить / изменить / удалить заметку
  /status   человекочитаемая страница мониторинга (здоровье, ресурсы, посещения)
  /health   health check (JSON, код 200 или 503)
  /metrics  метрики в формате Prometheus
"""

import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import Flask, jsonify, redirect, render_template, request, url_for

START_TIME = time.time()
VERSION = os.environ.get("APP_VERSION", "dev")
VISITS_KEEP_SECONDS = 7 * 24 * 3600

app = Flask(__name__)


# ---------------------------------------------------------------- база данных
def db_path():
    return os.environ.get("DB_PATH", "/data/notes.db")


@contextmanager
def db():
    path = db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS visits (ts REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS visits_ts ON visits (ts);
        """
    )
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_form():
    title = request.form.get("title", "").strip()[:200] or "Без названия"
    body = request.form.get("body", "").strip()[:5000]
    return title, body


# ------------------------------------------------------------------ интерфейс
@app.route("/")
def index():
    now = time.time()
    with db() as conn:
        # «посещение» = открытие главной страницы; /health и /metrics не считаем
        conn.execute("INSERT INTO visits (ts) VALUES (?)", (now,))
        conn.execute("DELETE FROM visits WHERE ts < ?", (now - VISITS_KEEP_SECONDS,))
        notes = conn.execute("SELECT * FROM notes ORDER BY id DESC").fetchall()
    return render_template("index.html", notes=notes)


@app.post("/notes/new")
def create_note():
    title, body = clean_form()
    with db() as conn:
        conn.execute(
            "INSERT INTO notes (title, body, updated_at) VALUES (?, ?, ?)",
            (title, body, utc_now()),
        )
    return redirect(url_for("index"))


@app.post("/notes/<int:note_id>/edit")
def edit_note(note_id):
    title, body = clean_form()
    with db() as conn:
        conn.execute(
            "UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?",
            (title, body, utc_now(), note_id),
        )
    return redirect(url_for("index"))


@app.post("/notes/<int:note_id>/delete")
def delete_note(note_id):
    with db() as conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    return redirect(url_for("index"))


# ------------------------------------------------------- сбор показателей
def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _meminfo():
    """MemTotal / MemAvailable из /proc/meminfo (внутри контейнера — это память хоста)."""
    values = {}
    text = _read("/proc/meminfo") or ""
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key in ("MemTotal", "MemAvailable"):
            values[key] = int(rest.split()[0]) * 1024
    return values.get("MemTotal"), values.get("MemAvailable")


def _cgroup_memory():
    """Память контейнера: (используется, лимит). Лимит None, если не задан."""
    usage = _read("/sys/fs/cgroup/memory.current")  # cgroup v2
    limit = _read("/sys/fs/cgroup/memory.max")
    if usage is None:  # cgroup v1
        usage = _read("/sys/fs/cgroup/memory/memory.usage_in_bytes")
        limit = _read("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    usage = int(usage) if usage and usage.isdigit() else None
    limit = int(limit) if limit and limit.isdigit() and int(limit) < 2**60 else None
    return usage, limit


def _cgroup_cpu_seconds():
    """Накопленное CPU-время контейнера в секундах."""
    stat = _read("/sys/fs/cgroup/cpu.stat")  # cgroup v2
    if stat:
        for line in stat.splitlines():
            if line.startswith("usage_usec"):
                return int(line.split()[1]) / 1e6
    usage = _read("/sys/fs/cgroup/cpuacct/cpuacct.usage")  # cgroup v1, наносекунды
    if usage and usage.isdigit():
        return int(usage) / 1e9
    t = os.times()  # запасной вариант: только процесс приложения
    return t.user + t.system


def _cpu_limit_cores():
    """Сколько ядер доступно контейнеру."""
    cpu_max = _read("/sys/fs/cgroup/cpu.max")  # cgroup v2: «квота период» или «max период»
    if cpu_max:
        quota, period = cpu_max.split()[:2]
        if quota != "max":
            return int(quota) / int(period)
    try:
        return float(len(os.sched_getaffinity(0)))
    except AttributeError:
        return float(os.cpu_count() or 1)


def _process_rss():
    status = _read("/proc/self/status") or ""
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    return None


def collect_stats():
    now = time.time()
    with db() as conn:
        last_hour = conn.execute(
            "SELECT COUNT(*) FROM visits WHERE ts >= ?", (now - 3600,)
        ).fetchone()[0]
        timestamps = [
            r[0]
            for r in conn.execute("SELECT ts FROM visits WHERE ts >= ?", (now - 24 * 3600,))
        ]
        notes_total = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

    # посещения по часам за последние сутки: индекс 0 — последний час
    hourly = [0] * 24
    for ts in timestamps:
        hourly[min(23, int((now - ts) // 3600))] += 1

    mem_total, mem_available = _meminfo()
    cg_usage, cg_limit = _cgroup_memory()
    disk = shutil.disk_usage("/")
    return {
        "version": VERSION,
        "uptime_seconds": now - START_TIME,
        "notes_total": notes_total,
        "visits_last_hour": last_hour,
        "visits_last_24h": len(timestamps),
        "visits_hourly": hourly,
        "container_memory_usage_bytes": cg_usage if cg_usage is not None else _process_rss(),
        "container_memory_limit_bytes": cg_limit or mem_total,
        "container_cpu_seconds": _cgroup_cpu_seconds(),
        "container_cpu_limit_cores": _cpu_limit_cores(),
        "host_memory_total_bytes": mem_total,
        "host_memory_available_bytes": mem_available,
        "disk_total_bytes": disk.total,
        "disk_free_bytes": disk.free,
    }


# ------------------------------------------------------------- health / metrics
@app.route("/health")
def health():
    try:
        with db() as conn:
            conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    body = {
        "status": "ok" if db_ok else "degraded",
        "db_ok": db_ok,
        "version": VERSION,
        "uptime_seconds": round(time.time() - START_TIME, 1),
    }
    return jsonify(body), (200 if db_ok else 503)


METRICS = [
    # (имя, тип, описание, ключ в collect_stats)
    ("app_uptime_seconds", "gauge", "Время работы приложения, секунды", "uptime_seconds"),
    ("app_visits_last_hour", "gauge", "Посещения главной страницы за последний час", "visits_last_hour"),
    ("app_visits_last_24h", "gauge", "Посещения главной страницы за последние 24 часа", "visits_last_24h"),
    ("app_notes_total", "gauge", "Количество заметок", "notes_total"),
    ("app_container_memory_usage_bytes", "gauge", "Память, потребляемая контейнером", "container_memory_usage_bytes"),
    ("app_container_memory_limit_bytes", "gauge", "Память, доступная контейнеру (лимит или вся память хоста)", "container_memory_limit_bytes"),
    ("app_container_cpu_usage_seconds_total", "counter", "Накопленное CPU-время контейнера, секунды", "container_cpu_seconds"),
    ("app_container_cpu_limit_cores", "gauge", "Ядер CPU, доступных контейнеру", "container_cpu_limit_cores"),
    ("app_host_memory_total_bytes", "gauge", "Всего памяти на хосте", "host_memory_total_bytes"),
    ("app_host_memory_available_bytes", "gauge", "Доступно памяти на хосте", "host_memory_available_bytes"),
    ("app_disk_total_bytes", "gauge", "Размер диска", "disk_total_bytes"),
    ("app_disk_free_bytes", "gauge", "Свободно на диске", "disk_free_bytes"),
]


@app.route("/metrics")
def metrics():
    stats = collect_stats()
    lines = [
        "# HELP app_info Версия приложения (значение всегда 1)",
        "# TYPE app_info gauge",
        f'app_info{{version="{VERSION}"}} 1',
    ]
    for name, mtype, help_text, key in METRICS:
        value = stats.get(key)
        if value is None:
            continue
        lines += [f"# HELP {name} {help_text}", f"# TYPE {name} {mtype}", f"{name} {value}"]
    text = "\n".join(lines) + "\n"
    return text, 200, {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"}


@app.route("/status")
def status():
    stats = collect_stats()
    # индекс 0 — последний час; в таблице самый свежий период сверху
    hourly = [(f"{i}–{i + 1} ч назад", n) for i, n in enumerate(stats["visits_hourly"])]
    return render_template("status.html", s=stats, hourly=hourly)


@app.template_filter("mb")
def mb(value):
    return "—" if value is None else f"{value / 1024 / 1024:,.0f} МБ".replace(",", " ")


@app.template_filter("ts")
def ts(value):
    return value[:16].replace("T", " ") + " UTC"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

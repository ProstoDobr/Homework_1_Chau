#!/usr/bin/env bash
# Локальный запуск всего стека одной командой (нужны Docker и Docker Compose).
set -euo pipefail
cd "$(dirname "$0")/.."

GIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo local)" docker compose up -d --build
./scripts/wait_health.sh http://localhost:8000/health

cat <<'MSG'

Приложение:  http://localhost:8000
Статус:      http://localhost:8000/status
Метрики:     http://localhost:8000/metrics
Prometheus:  http://localhost:9090
Grafana:     http://localhost:3000   (дашборд открывается сразу, без логина)

Остановить:  docker compose down      (с удалением данных: docker compose down -v)
MSG

#!/usr/bin/env bash
# Быстрый локальный запуск всего стека одной командой — удобно, чтобы
# преподаватель мог сам проверить исходники без доступа к вашему серверу.
set -euo pipefail

echo "==> Собираю и поднимаю приложение + мониторинг локально"
docker compose up -d --build

sleep 3
echo "==> Проверка health check:"
curl -fsS http://localhost:8000/health && echo

cat <<EOF

Готово! Открой в браузере:
  Приложение:  http://localhost:8000
  Метрики:     http://localhost:8000/metrics
  Prometheus:  http://localhost:9090
  Grafana:     http://localhost:3000  (admin/admin)

Остановить всё:  docker compose down
EOF

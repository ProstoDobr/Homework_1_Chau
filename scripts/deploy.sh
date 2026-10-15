#!/usr/bin/env bash
# Развёртывание из артефакта сборки. Запускается на сервере (или локально),
# где установлены Docker и Docker Compose:
#   ./scripts/deploy.sh artifacts/homework1-app-<коммит>.tar.gz
# Данные (volume app-data) при этом сохраняются.
set -euo pipefail
cd "$(dirname "$0")/.."

ARTIFACT="${1:?Использование: $0 <файл-артефакта.tar.gz>}"
IMAGE_NAME="${IMAGE_NAME:-homework1-app}"
APP_PORT="${APP_PORT:-8000}"

echo "==> Загрузка образа из ${ARTIFACT}"
LOADED="$(docker load -i "${ARTIFACT}" | awk '/^Loaded image:/ {print $3}' | tail -n1)"
[ -n "${LOADED}" ] || { echo "В артефакте не найден образ" >&2; exit 1; }
docker tag "${LOADED}" "${IMAGE_NAME}:latest"

echo "==> Запуск приложения и мониторинга (пересоздаётся только изменившееся)"
APP_IMAGE="${IMAGE_NAME}:latest" docker compose up -d --no-build

./scripts/wait_health.sh "http://localhost:${APP_PORT}/health"

echo "Приложение:  http://<адрес сервера>:${APP_PORT}"
echo "Статус:      http://<адрес сервера>:${APP_PORT}/status"
echo "Prometheus:  http://<адрес сервера>:9090"
echo "Grafana:     http://<адрес сервера>:3000"

#!/usr/bin/env bash
# Разворачивает приложение на сервере из сохранённого артефакта сборки.
# Предполагается, что этот скрипт запускается НА СЕРВЕРЕ (или по ssh),
# а рядом лежит файл артефакта (*.tar), полученный из scripts/build.sh,
# и файл docker-compose.yml + monitoring/prometheus.yml.
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-homework1-app}"
ARTIFACT_PATH="${1:?Укажи путь к .tar артефакту, например: ./scripts/deploy.sh ./artifacts/homework1-app-abc123.tar}"

echo "==> Загружаю образ из артефакта ${ARTIFACT_PATH}"
docker load -i "${ARTIFACT_PATH}"

echo "==> Помечаю образ как ${IMAGE_NAME}:latest, чтобы его подхватил docker-compose"
LOADED_TAG=$(docker load -i "${ARTIFACT_PATH}" | tail -n1 | awk '{print $NF}')
docker tag "${LOADED_TAG}" "${IMAGE_NAME}:latest" || true

echo "==> Поднимаю (или пересоздаю) стек приложения + мониторинга"
APP_IMAGE="${IMAGE_NAME}:latest" docker compose up -d --force-recreate app

echo "==> Поднимаю мониторинг (если ещё не запущен)"
docker compose up -d node-exporter cadvisor prometheus grafana

echo "==> Готово. Проверка:"
sleep 3
curl -fsS http://localhost:8000/health && echo
echo "Приложение:      http://<SERVER_IP>:8000"
echo "Метрики app:      http://<SERVER_IP>:8000/metrics"
echo "Prometheus:       http://<SERVER_IP>:9090"
echo "Grafana:          http://<SERVER_IP>:3000  (admin/admin)"

#!/usr/bin/env bash
# Собирает Docker-образ приложения и сохраняет его как файл-артефакт (.tar),
# который потом можно перенести на сервер и развернуть, не пересобирая заново.
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-homework1-app}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%s)}"
ARTIFACT_DIR="${ARTIFACT_DIR:-./artifacts}"

echo "==> Собираю образ ${IMAGE_NAME}:${IMAGE_TAG}"
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" -t "${IMAGE_NAME}:latest" .

mkdir -p "${ARTIFACT_DIR}"
ARTIFACT_PATH="${ARTIFACT_DIR}/${IMAGE_NAME}-${IMAGE_TAG}.tar"

echo "==> Сохраняю артефакт сборки в ${ARTIFACT_PATH}"
docker save "${IMAGE_NAME}:${IMAGE_TAG}" -o "${ARTIFACT_PATH}"

echo "==> Готово. Артефакт: ${ARTIFACT_PATH}"
echo "    Его можно скопировать на сервер (scp) и развернуть через scripts/deploy.sh"

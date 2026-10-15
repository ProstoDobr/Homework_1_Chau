#!/usr/bin/env bash
# Сборка: образ + сохранение артефакта (artifacts/<имя>-<коммит>.tar.gz).
# Артефакт можно перенести на сервер и развернуть через scripts/deploy.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE_NAME="${IMAGE_NAME:-homework1-app}"
GIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo dev)"
IMAGE_TAG="${IMAGE_TAG:-${GIT_SHA:0:7}}"
ARTIFACT_DIR="${ARTIFACT_DIR:-artifacts}"
ARTIFACT="${ARTIFACT_DIR}/${IMAGE_NAME}-${IMAGE_TAG}.tar.gz"

echo "==> Сборка образа ${IMAGE_NAME}:${IMAGE_TAG}"
docker build --build-arg GIT_SHA="${GIT_SHA}" \
  -t "${IMAGE_NAME}:${IMAGE_TAG}" -t "${IMAGE_NAME}:latest" .

echo "==> Сохранение артефакта ${ARTIFACT}"
mkdir -p "${ARTIFACT_DIR}"
docker save "${IMAGE_NAME}:${IMAGE_TAG}" | gzip > "${ARTIFACT}"

echo "==> Готово: ${ARTIFACT} ($(du -h "${ARTIFACT}" | cut -f1))"

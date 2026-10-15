#!/usr/bin/env bash
# Ждёт, пока /health ответит 200. Использование: wait_health.sh [URL] [число попыток]
set -euo pipefail

URL="${1:-http://localhost:8000/health}"
TRIES="${2:-30}"

for _ in $(seq 1 "${TRIES}"); do
  if body="$(curl -fsS "${URL}" 2>/dev/null)"; then
    echo "==> health check пройден: ${body}"
    exit 0
  fi
  sleep 2
done

echo "health check не пройден: ${URL}" >&2
exit 1

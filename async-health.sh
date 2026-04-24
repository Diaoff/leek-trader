#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"
RUN_DIR="$ROOT_DIR/.local/run"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
CELERY_WORKER_PID_FILE="$RUN_DIR/celery-worker.pid"
CELERY_BEAT_PID_FILE="$RUN_DIR/celery-beat.pid"
VENV_DIR="$ROOT_DIR/.venv"
CELERY_BIN="$VENV_DIR/bin/celery"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}/api/v1/health}"
ASYNC_SUMMARY_URL="${ASYNC_SUMMARY_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}/api/v1/monitoring/async-tasks/summary}"
DEFAULT_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/leek_trader"
DEFAULT_REDIS_URL="redis://127.0.0.1:6379/0"
ENV_FILE_DATABASE_URL=""
ENV_FILE_REDIS_URL=""

if [[ -f "$ENV_FILE" ]]; then
  ENV_FILE_DATABASE_URL="$(awk -F= '/^DATABASE_URL=/{sub(/^[^=]*=/,""); print; exit}' "$ENV_FILE")"
  ENV_FILE_REDIS_URL="$(awk -F= '/^REDIS_URL=/{sub(/^[^=]*=/,""); print; exit}' "$ENV_FILE")"
fi

BACKEND_DATABASE_URL="${DATABASE_URL:-${ENV_FILE_DATABASE_URL:-$DEFAULT_DATABASE_URL}}"
BACKEND_REDIS_URL="${REDIS_URL:-${ENV_FILE_REDIS_URL:-$DEFAULT_REDIS_URL}}"
EXIT_CODE=0

usage() {
  cat <<EOF
Usage: ./async-health.sh

Checks:
  - backend health endpoint reachability
  - async summary endpoint reachability
  - local Celery worker/beat PID liveness
  - Celery inspect ping response from at least one worker
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

check_pid() {
  local name="$1"
  local pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "[fail] $name PID file is missing: $pid_file"
    EXIT_CODE=1
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if [[ -z "$pid" ]] || ! kill -0 "$pid" >/dev/null 2>&1; then
    echo "[fail] $name is not running (stale PID file: $pid_file)"
    EXIT_CODE=1
    return
  fi

  echo "[ok]   $name is running (PID $pid)"
}

check_url() {
  local name="$1"
  local url="$2"
  if curl -fsS "$url" >/dev/null 2>&1; then
    echo "[ok]   $name is reachable: $url"
    return
  fi

  echo "[fail] $name is unreachable: $url"
  EXIT_CODE=1
}

check_worker_ping() {
  if [[ ! -x "$CELERY_BIN" ]]; then
    echo "[fail] Celery binary is missing: $CELERY_BIN"
    EXIT_CODE=1
    return
  fi

  local output
  if output="$(
    cd "$ROOT_DIR/backend"
    export DATABASE_URL="$BACKEND_DATABASE_URL"
    export REDIS_URL="$BACKEND_REDIS_URL"
    export PYTHONPATH="$ROOT_DIR/backend"
    "$CELERY_BIN" -A app.core.celery_app.celery_app inspect ping --timeout=2 2>&1
  )"; then
    echo "[ok]   Celery inspect ping succeeded"
    echo "$output"
    return
  fi

  echo "[fail] Celery inspect ping failed"
  echo "$output"
  EXIT_CODE=1
}

echo "Leek Trader async health check"
check_url "Backend health endpoint" "$BACKEND_HEALTH_URL"
check_url "Async summary endpoint" "$ASYNC_SUMMARY_URL"
check_pid "Celery worker" "$CELERY_WORKER_PID_FILE"
check_pid "Celery beat" "$CELERY_BEAT_PID_FILE"
check_worker_ping

exit "$EXIT_CODE"

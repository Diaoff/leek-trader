#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"
RUN_DIR="$ROOT_DIR/.local/run"
LOG_DIR="$ROOT_DIR/.local/logs"
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
WATCH_MODE=0
WATCH_INTERVAL_SECONDS=15
WATCH_MAX_FAILURES=3
WATCH_MAX_CHECKS=0
GUARD_LOG_FILE="$LOG_DIR/async-guard.log"
CHECK_FAILURES=()

usage() {
  cat <<EOF
Usage: ./async-health.sh [--watch] [--interval <seconds>] [--max-failures <count>] [--max-checks <count>] [--log-file <path>]

Checks:
  - backend health endpoint reachability
  - async summary endpoint reachability
  - local Celery worker/beat PID liveness
  - Celery inspect ping response from at least one worker

Recovery:
  - rerun with live services after ./restart.sh --with-async

Watch mode:
  - loop health checks and emit local guard alerts after consecutive failures
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --watch)
      WATCH_MODE=1
      shift
      ;;
    --interval)
      WATCH_INTERVAL_SECONDS="${2:?missing value for --interval}"
      shift 2
      ;;
    --max-failures)
      WATCH_MAX_FAILURES="${2:?missing value for --max-failures}"
      shift 2
      ;;
    --max-checks)
      WATCH_MAX_CHECKS="${2:?missing value for --max-checks}"
      shift 2
      ;;
    --log-file)
      GUARD_LOG_FILE="${2:?missing value for --log-file}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

mkdir -p "$RUN_DIR" "$LOG_DIR"

if [[ "$GUARD_LOG_FILE" == */* ]]; then
  mkdir -p "$(dirname "$GUARD_LOG_FILE")"
fi

timestamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

record_failure() {
  local failure_key="$1"
  EXIT_CODE=1
  CHECK_FAILURES+=("$failure_key")
}

join_failures() {
  local joined=""
  local failure
  for failure in "${CHECK_FAILURES[@]}"; do
    if [[ -n "$joined" ]]; then
      joined+=","
    fi
    joined+="$failure"
  done
  printf '%s' "$joined"
}

classify_guard_severity() {
  local consecutive_failures="$1"
  if (( consecutive_failures >= WATCH_MAX_FAILURES )); then
    printf '%s' "critical"
    return
  fi
  printf '%s' "warning"
}

emit_guard_alert() {
  local severity="$1"
  local consecutive_failures="$2"
  local iteration="$3"
  local failed_checks
  failed_checks="$(join_failures)"
  local alert_line
  alert_line="$(printf 'ASYNC_LOCAL_GUARD_ALERT ts=%s severity=%s consecutive_failures=%s iteration=%s failed_checks=%s backend=%s summary=%s' "$(timestamp)" "$severity" "$consecutive_failures" "$iteration" "${failed_checks:-none}" "$BACKEND_HEALTH_URL" "$ASYNC_SUMMARY_URL")"
  printf '%s\n' "$alert_line" | tee -a "$GUARD_LOG_FILE"
}

check_pid() {
  local name="$1"
  local pid_file="$2"
  local failure_key_prefix="$3"
  if [[ ! -f "$pid_file" ]]; then
    echo "[fail] $name PID file is missing: $pid_file"
    record_failure "${failure_key_prefix}_pid_missing"
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if [[ -z "$pid" ]] || ! kill -0 "$pid" >/dev/null 2>&1; then
    echo "[fail] $name is not running (stale PID file: $pid_file)"
    record_failure "${failure_key_prefix}_pid_stale"
    return
  fi

  echo "[ok]   $name is running (PID $pid)"
}

show_recent_log() {
  local name="$1"
  local log_file="$2"
  local lines="${3:-40}"

  if [[ ! -f "$log_file" ]]; then
    return
  fi

  echo "[info] recent ${name} log tail (${log_file})"
  tail -n "$lines" "$log_file" || true
}

check_url() {
  local name="$1"
  local url="$2"
  local failure_key="$3"
  if curl -fsS "$url" >/dev/null 2>&1; then
    echo "[ok]   $name is reachable: $url"
    return
  fi

  echo "[fail] $name is unreachable: $url"
  record_failure "$failure_key"
}

check_worker_ping() {
  if [[ ! -x "$CELERY_BIN" ]]; then
    echo "[fail] Celery binary is missing: $CELERY_BIN"
    record_failure "celery_binary_missing"
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
  record_failure "celery_inspect_ping_failed"
}

print_recovery_hint() {
  if [[ "$EXIT_CODE" == "0" ]]; then
    return
  fi

  echo "[hint] Recovery commands:"
  echo "       ./stop.sh"
  echo "       ./start.sh --with-async"
  echo "       bash ./async-health.sh"
  echo "       bash ./async-health.sh --watch --interval 15 --max-failures 3"
  echo "[hint] If only Redis is missing, start it first: docker compose up -d redis"
}

run_health_check() {
  EXIT_CODE=0
  CHECK_FAILURES=()

  echo "Leek Trader async health check"
  check_url "Backend health endpoint" "$BACKEND_HEALTH_URL" "backend_health_unreachable"
  check_url "Async summary endpoint" "$ASYNC_SUMMARY_URL" "async_summary_unreachable"
  check_pid "Celery worker" "$CELERY_WORKER_PID_FILE" "celery_worker"
  check_pid "Celery beat" "$CELERY_BEAT_PID_FILE" "celery_beat"
  check_worker_ping
  if [[ "$EXIT_CODE" != "0" ]]; then
    show_recent_log "Celery worker" "$ROOT_DIR/.local/logs/celery-worker.log" 20
    show_recent_log "Celery beat" "$ROOT_DIR/.local/logs/celery-beat.log" 20
  fi
  print_recovery_hint

  return "$EXIT_CODE"
}

run_watch_mode() {
  local consecutive_failures=0
  local iteration=0

  echo "[watch] interval=${WATCH_INTERVAL_SECONDS}s max_failures=${WATCH_MAX_FAILURES} max_checks=${WATCH_MAX_CHECKS} log_file=${GUARD_LOG_FILE}"

  while true; do
    iteration=$((iteration + 1))
    echo "[watch] check #${iteration}"

    if run_health_check; then
      if (( consecutive_failures > 0 )); then
        echo "[watch] recovered after ${consecutive_failures} consecutive failure(s)"
      fi
      consecutive_failures=0
    else
      consecutive_failures=$((consecutive_failures + 1))
      emit_guard_alert "$(classify_guard_severity "$consecutive_failures")" "$consecutive_failures" "$iteration"
      if (( consecutive_failures >= WATCH_MAX_FAILURES )); then
        echo "[watch] reached max consecutive failures (${WATCH_MAX_FAILURES}); stopping"
        return 1
      fi
    fi

    if (( WATCH_MAX_CHECKS > 0 && iteration >= WATCH_MAX_CHECKS )); then
      echo "[watch] completed ${iteration} check(s)"
      return 0
    fi

    sleep "$WATCH_INTERVAL_SECONDS"
  done
}

if [[ "$WATCH_MODE" == "1" ]]; then
  run_watch_mode
  exit $?
fi

run_health_check
exit $?

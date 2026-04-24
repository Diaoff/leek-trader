#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.local/run"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
CELERY_WORKER_PID_FILE="$RUN_DIR/celery-worker.pid"
CELERY_BEAT_PID_FILE="$RUN_DIR/celery-beat.pid"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

listening_pid() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
}

process_cwd() {
  local pid="$1"
  lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
}

wait_for_pid_exit() {
  local pid="$1"
  for _ in $(seq 1 10); do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  return 1
}

stop_pid() {
  local name="$1"
  local pid="$2"
  local pid_file="${3:-}"

  echo "Stopping $name (PID $pid)..."
  kill "$pid"

  if wait_for_pid_exit "$pid"; then
    [[ -n "$pid_file" ]] && rm -f "$pid_file"
    echo "$name stopped."
    return 0
  fi

  echo "$name did not exit in time; forcing stop."
  kill -9 "$pid"
  [[ -n "$pid_file" ]] && rm -f "$pid_file"
}

stop_repo_port_process() {
  local name="$1"
  local host="$2"
  local port="$3"
  local expected_cwd="$4"
  local pid_file="$5"
  local pid

  pid="$(listening_pid "$port")"
  if [[ -z "$pid" ]]; then
    echo "$name is not running."
    return 0
  fi

  local cwd
  cwd="$(process_cwd "$pid")"
  if [[ "$cwd" != "$expected_cwd" ]]; then
    echo "$name is not running."
    echo "$name port ${host}:${port} is owned by external PID $pid; leaving it running."
    return 0
  fi

  stop_pid "$name" "$pid" "$pid_file"
}

stop_process() {
  local name="$1"
  local pid_file="$2"
  local host="${3:-}"
  local port="${4:-}"
  local expected_cwd="${5:-}"
  if [[ ! -f "$pid_file" ]]; then
    if [[ -n "$port" ]] && [[ -n "$expected_cwd" ]]; then
      stop_repo_port_process "$name" "$host" "$port" "$expected_cwd" "$pid_file"
      return 0
    fi

    echo "$name is not running."
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"
  if [[ -z "$pid" ]] || ! kill -0 "$pid" >/dev/null 2>&1; then
    rm -f "$pid_file"
    if [[ -n "$port" ]] && [[ -n "$expected_cwd" ]]; then
      echo "$name PID file was stale and has been cleaned up."
      stop_repo_port_process "$name" "$host" "$port" "$expected_cwd" "$pid_file"
      return 0
    fi

    echo "$name PID file was stale and has been cleaned up."
    return 0
  fi

  stop_pid "$name" "$pid" "$pid_file"
}

stop_process "Celery beat" "$CELERY_BEAT_PID_FILE"
stop_process "Celery worker" "$CELERY_WORKER_PID_FILE"
stop_process "Frontend" "$FRONTEND_PID_FILE" "$FRONTEND_HOST" "$FRONTEND_PORT" "$ROOT_DIR/frontend"
stop_process "Backend" "$BACKEND_PID_FILE" "$BACKEND_HOST" "$BACKEND_PORT" "$ROOT_DIR/backend"

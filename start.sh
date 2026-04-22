#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.local/run"
LOG_DIR="$ROOT_DIR/.local/logs"
DATA_DIR="$ROOT_DIR/.local/data"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_LOG_FILE="$LOG_DIR/backend.log"
FRONTEND_LOG_FILE="$LOG_DIR/frontend.log"
FRONTEND_URL_FILE="$RUN_DIR/frontend.url"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_URL="${BACKEND_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}/}"
FRONTEND_URL="${FRONTEND_URL:-}"
SQLITE_PATH="$DATA_DIR/leek_trader.db"
BACKEND_DATABASE_URL="${DATABASE_URL:-sqlite:///$SQLITE_PATH}"
if [[ "$BACKEND_DATABASE_URL" == sqlite://* ]]; then
  DATABASE_DISPLAY="$BACKEND_DATABASE_URL"
else
  DATABASE_DISPLAY="custom DATABASE_URL"
fi
BACKEND_STARTED_BY_SCRIPT=0
FRONTEND_STARTED_BY_SCRIPT=0

mkdir -p "$RUN_DIR" "$LOG_DIR" "$DATA_DIR"

cleanup_started_processes() {
  if [[ "$FRONTEND_STARTED_BY_SCRIPT" == "1" ]] && [[ -f "$FRONTEND_PID_FILE" ]]; then
    local frontend_pid
    frontend_pid="$(cat "$FRONTEND_PID_FILE")"
    if [[ -n "$frontend_pid" ]] && kill -0 "$frontend_pid" >/dev/null 2>&1; then
      kill "$frontend_pid" >/dev/null 2>&1 || true
    fi
    rm -f "$FRONTEND_PID_FILE"
  fi

  if [[ "$BACKEND_STARTED_BY_SCRIPT" == "1" ]] && [[ -f "$BACKEND_PID_FILE" ]]; then
    local backend_pid
    backend_pid="$(cat "$BACKEND_PID_FILE")"
    if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" >/dev/null 2>&1; then
      kill "$backend_pid" >/dev/null 2>&1 || true
    fi
    rm -f "$BACKEND_PID_FILE"
  fi
}

on_error() {
  cleanup_started_processes
}

trap on_error ERR

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid="$(cat "$pid_file")"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

cleanup_stale_pid() {
  local pid_file="$1"
  if is_running "$pid_file"; then
    return 0
  fi
  rm -f "$pid_file"
  return 1
}

listening_pid() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
}

ensure_port_available() {
  local name="$1"
  local host="$2"
  local port="$3"
  local pid_file="$4"

  cleanup_stale_pid "$pid_file" || true

  local active_pid
  active_pid="$(listening_pid "$port")"
  if [[ -z "$active_pid" ]]; then
    return 0
  fi

  if [[ -f "$pid_file" ]] && [[ "$(cat "$pid_file")" == "$active_pid" ]]; then
    return 0
  fi

  echo "Error: $name port ${host}:${port} is already in use by PID $active_pid." >&2
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >&2 || true
  exit 1
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local timeout="${3:-30}"
  local elapsed=0

  while (( elapsed < timeout )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  echo "Error: $name did not become ready within ${timeout}s." >&2
  return 1
}

wait_for_service() {
  local name="$1"
  local url="$2"
  local pid_file="$3"
  local log_file="$4"
  local timeout="${5:-30}"
  local elapsed=0

  while (( elapsed < timeout )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi

    if ! is_running "$pid_file"; then
      echo "Error: $name exited before becoming ready." >&2
      if [[ -f "$log_file" ]]; then
        tail -n 80 "$log_file" >&2
      fi
      return 1
    fi

    sleep 1
    elapsed=$((elapsed + 1))
  done

  echo "Error: $name did not become ready within ${timeout}s." >&2
  if [[ -f "$log_file" ]]; then
    tail -n 80 "$log_file" >&2
  fi
  return 1
}

resolve_frontend_url() {
  local timeout="${1:-30}"
  local elapsed=0
  local discovered_url=""

  while (( elapsed < timeout )); do
    discovered_url="$(grep -Eo 'http://[^[:space:]]+' "$FRONTEND_LOG_FILE" 2>/dev/null | tail -n 1 || true)"
    if [[ -n "$discovered_url" ]]; then
      FRONTEND_URL="$discovered_url"
      printf '%s\n' "$FRONTEND_URL" >"$FRONTEND_URL_FILE"
      return 0
    fi

    if ! is_running "$FRONTEND_PID_FILE"; then
      echo "Error: Frontend exited before reporting its URL." >&2
      if [[ -f "$FRONTEND_LOG_FILE" ]]; then
        tail -n 80 "$FRONTEND_LOG_FILE" >&2
      fi
      return 1
    fi

    sleep 1
    elapsed=$((elapsed + 1))
  done

  echo "Error: Frontend URL could not be determined from $FRONTEND_LOG_FILE within ${timeout}s." >&2
  if [[ -f "$FRONTEND_LOG_FILE" ]]; then
    tail -n 40 "$FRONTEND_LOG_FILE" >&2
  fi
  return 1
}

ensure_process_started() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"

  sleep 1
  if is_running "$pid_file"; then
    return 0
  fi

  echo "Error: $name failed to start. Recent log output:" >&2
  if [[ -f "$log_file" ]]; then
    tail -n 40 "$log_file" >&2
  fi
  exit 1
}

ensure_backend_runtime() {
  if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
  fi

  if ! "$VENV_PYTHON" -c "import uvicorn" >/dev/null 2>&1; then
    echo "Installing backend dependencies..."
    "$VENV_PYTHON" -m pip install -r "$ROOT_DIR/backend/requirements.txt"
  fi
}

ensure_frontend_runtime() {
  if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
    echo "Installing frontend dependencies..."
    (cd "$ROOT_DIR/frontend" && npm install)
  fi
}

start_backend() {
  ensure_port_available "Backend" "$BACKEND_HOST" "$BACKEND_PORT" "$BACKEND_PID_FILE"

  if is_running "$BACKEND_PID_FILE"; then
    echo "Backend is already running with PID $(cat "$BACKEND_PID_FILE")."
    return 0
  fi

  echo "Starting backend..."
  : >"$BACKEND_LOG_FILE"
  (
    cd "$ROOT_DIR/backend"
    export DATABASE_URL="$BACKEND_DATABASE_URL"
    export VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}/api/v1}"
    export PYTHONPATH="$ROOT_DIR/backend"
    nohup "$VENV_PYTHON" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" >"$BACKEND_LOG_FILE" 2>&1 &
    echo $! >"$BACKEND_PID_FILE"
  )
  BACKEND_STARTED_BY_SCRIPT=1

  ensure_process_started "Backend" "$BACKEND_PID_FILE" "$BACKEND_LOG_FILE"
}

start_frontend() {
  if is_running "$FRONTEND_PID_FILE"; then
    echo "Frontend is already running with PID $(cat "$FRONTEND_PID_FILE")."
    if [[ -f "$FRONTEND_URL_FILE" ]]; then
      FRONTEND_URL="$(cat "$FRONTEND_URL_FILE")"
    fi
    return 0
  fi

  echo "Starting frontend..."
  : >"$FRONTEND_LOG_FILE"
  rm -f "$FRONTEND_URL_FILE"
  (
    cd "$ROOT_DIR/frontend"
    export VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}/api/v1}"
    nohup npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" >"$FRONTEND_LOG_FILE" 2>&1 &
    echo $! >"$FRONTEND_PID_FILE"
  )
  FRONTEND_STARTED_BY_SCRIPT=1

  ensure_process_started "Frontend" "$FRONTEND_PID_FILE" "$FRONTEND_LOG_FILE"
}

ensure_backend_runtime
ensure_frontend_runtime
start_backend
start_frontend

if [[ -z "$FRONTEND_URL" ]]; then
  resolve_frontend_url 30
fi
wait_for_service "Backend" "$BACKEND_URL" "$BACKEND_PID_FILE" "$BACKEND_LOG_FILE" 30
wait_for_service "Frontend" "$FRONTEND_URL" "$FRONTEND_PID_FILE" "$FRONTEND_LOG_FILE" 30
trap - ERR

cat <<EOF
Leek Trader local services are running.
Frontend: ${FRONTEND_URL}
Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}
Database: ${DATABASE_DISPLAY}
Logs:     $LOG_DIR
EOF

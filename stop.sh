#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.local/run"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"

stop_process() {
  local name="$1"
  local pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "$name is not running."
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"
  if [[ -z "$pid" ]] || ! kill -0 "$pid" >/dev/null 2>&1; then
    rm -f "$pid_file"
    echo "$name PID file was stale and has been cleaned up."
    return 0
  fi

  echo "Stopping $name (PID $pid)..."
  kill "$pid"

  for _ in $(seq 1 10); do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      rm -f "$pid_file"
      echo "$name stopped."
      return 0
    fi
    sleep 1
  done

  echo "$name did not exit in time; forcing stop."
  kill -9 "$pid"
  rm -f "$pid_file"
}

stop_process "Frontend" "$FRONTEND_PID_FILE"
stop_process "Backend" "$BACKEND_PID_FILE"

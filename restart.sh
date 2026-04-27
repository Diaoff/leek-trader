#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

START_ARGS=()
START_ARGS_COUNT=0
INJECT_ASYNC=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --without-async)
      INJECT_ASYNC=0
      shift
      ;;
    --with-async)
      INJECT_ASYNC=0
      START_ARGS+=("$1")
      START_ARGS_COUNT=$((START_ARGS_COUNT + 1))
      shift
      ;;
    *)
      START_ARGS+=("$1")
      START_ARGS_COUNT=$((START_ARGS_COUNT + 1))
      shift
      ;;
  esac
done

if [[ "$INJECT_ASYNC" == "1" ]]; then
  if [[ "$START_ARGS_COUNT" -gt 0 ]]; then
    START_ARGS=(--with-async "${START_ARGS[@]}")
  else
    START_ARGS=(--with-async)
  fi
  START_ARGS_COUNT=$((START_ARGS_COUNT + 1))
fi

"$ROOT_DIR/stop.sh"
if [[ "$START_ARGS_COUNT" -gt 0 ]]; then
  "$ROOT_DIR/start.sh" "${START_ARGS[@]}"
else
  "$ROOT_DIR/start.sh"
fi

#!/usr/bin/env bash

set -Eeuo pipefail

APP_NAME="${APP_NAME:-leek-trader}"
IMAGE_NAME="${IMAGE_NAME:-leek-trader:all-in-one}"
HTTP_PORT="${HTTP_PORT:-10086}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-leek_trader_prod}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
PG_VOLUME="${PG_VOLUME:-leek_trader_pgdata}"
REBUILD_IMAGE="${REBUILD_IMAGE:-auto}"
SKIP_FRONTEND_BUILD="${SKIP_FRONTEND_BUILD:-0}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

log() {
  printf '[deploy] %s\n' "$*"
}

fail() {
  printf '[deploy] Error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command '$1'. Please install it first."
}

ensure_project_root() {
  [[ -f Dockerfile.all-in-one ]] || fail "Dockerfile.all-in-one not found. Run this script from the extracted project root."
  [[ -d backend && -f backend/requirements.txt ]] || fail "backend/requirements.txt not found. Is the zip fully extracted?"
  [[ -d frontend && -f frontend/package.json ]] || fail "frontend/package.json not found. Is the zip fully extracted?"
}

check_ports() {
  local port
  for port in "$HTTP_PORT" "$POSTGRES_PORT"; do
    if docker ps --format '{{.Names}} {{.Ports}}' | grep -v "^${APP_NAME} " | grep -q ":${port}->"; then
      fail "host port ${port} is already used by another Docker container. Override with HTTP_PORT or POSTGRES_PORT."
    fi
  done
}

build_frontend() {
  if [[ "$SKIP_FRONTEND_BUILD" == "1" ]]; then
    [[ -d frontend/dist ]] || fail "SKIP_FRONTEND_BUILD=1 but frontend/dist does not exist."
    log "skipping frontend build"
    return
  fi

  require_command npm
  log "installing frontend dependencies"
  npm --prefix frontend ci
  log "building frontend assets"
  npm --prefix frontend run build
}

build_image() {
  local image_exists=0
  if docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    image_exists=1
  fi

  if [[ "$REBUILD_IMAGE" == "1" || "$REBUILD_IMAGE" == "true" || "$REBUILD_IMAGE" == "yes" ]]; then
    log "building Docker image $IMAGE_NAME"
    docker build -f Dockerfile.all-in-one -t "$IMAGE_NAME" .
    return
  fi

  if [[ "$REBUILD_IMAGE" == "0" || "$REBUILD_IMAGE" == "false" || "$REBUILD_IMAGE" == "no" ]]; then
    [[ "$image_exists" == "1" ]] || fail "image $IMAGE_NAME does not exist and REBUILD_IMAGE=0 was set."
    log "using existing Docker image $IMAGE_NAME"
    return
  fi

  if [[ "$image_exists" == "1" ]]; then
    log "using existing Docker image $IMAGE_NAME (set REBUILD_IMAGE=1 to rebuild)"
  else
    log "Docker image not found; building $IMAGE_NAME"
    docker build -f Dockerfile.all-in-one -t "$IMAGE_NAME" .
  fi
}

restart_container() {
  log "stopping old container if present"
  docker rm -f "$APP_NAME" >/dev/null 2>&1 || true

  log "starting container $APP_NAME"
  docker run -d \
    --name "$APP_NAME" \
    --restart unless-stopped \
    -p "${HTTP_PORT}:80" \
    -p "${POSTGRES_PORT}:5432" \
    -v "$ROOT_DIR/backend:/app/backend" \
    -v "$ROOT_DIR/frontend/dist:/app/frontend/dist" \
    -v "${PG_VOLUME}:/var/lib/postgresql/data" \
    -e "POSTGRES_DB=${POSTGRES_DB}" \
    -e "POSTGRES_USER=${POSTGRES_USER}" \
    -e "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \
    "$IMAGE_NAME" >/dev/null
}

wait_for_health() {
  local url="http://127.0.0.1:${HTTP_PORT}/health"
  local attempt

  log "waiting for backend health check"
  for attempt in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "health check passed"
      return
    fi
    sleep 2
  done

  docker logs --tail 120 "$APP_NAME" >&2 || true
  fail "container did not become healthy at ${url}"
}

main() {
  ensure_project_root
  require_command docker
  require_command curl

  check_ports
  build_frontend
  build_image
  restart_container
  wait_for_health

  cat <<MSG

Deploy complete.
Frontend:   http://127.0.0.1:${HTTP_PORT}
Backend:    http://127.0.0.1:${HTTP_PORT}/health
API docs:   http://127.0.0.1:${HTTP_PORT}/docs
PostgreSQL: 127.0.0.1:${POSTGRES_PORT} db=${POSTGRES_DB} user=${POSTGRES_USER}
Logs:       docker logs -f ${APP_NAME}

Update from a new uploaded zip:
  unzip the new package over this directory, then run ./deploy-centos-all-in-one.sh again.
  Use REBUILD_IMAGE=1 ./deploy-centos-all-in-one.sh when backend requirements, Dockerfile, or entrypoint changed.
MSG
}

main "$@"

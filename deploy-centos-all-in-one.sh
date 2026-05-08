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
ZIP_PATH="${ZIP_PATH:-/home/diaoff/leek-trader-dev.zip}"
WORK_DIR="${WORK_DIR:-/home/diaoff/leek-trader}"
REBUILD_IMAGE="${REBUILD_IMAGE:-0}"
SKIP_FRONTEND_BUILD="${SKIP_FRONTEND_BUILD:-0}"
DOCKER_CMD="${DOCKER_CMD:-}"
APT_MIRROR="${APT_MIRROR:-}"
APT_SECURITY_MIRROR="${APT_SECURITY_MIRROR:-}"
PIP_INDEX_URL="${PIP_INDEX_URL:-}"
INSTALL_RL_DEPS="${INSTALL_RL_DEPS:-0}"

usage() {
  cat <<EOF_USAGE
Usage: $0 [zip_path]
       $0 --zip /path/to/leek-trader-dev.zip

Environment overrides:
  ZIP_PATH, WORK_DIR, HTTP_PORT, POSTGRES_PORT, POSTGRES_PASSWORD, REBUILD_IMAGE, SKIP_FRONTEND_BUILD, DOCKER_CMD, APT_MIRROR, APT_SECURITY_MIRROR, PIP_INDEX_URL, INSTALL_RL_DEPS
EOF_USAGE
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --zip)
        [[ $# -ge 2 ]] || fail "--zip requires a path"
        ZIP_PATH="$2"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      --*)
        fail "unknown option: $1"
        ;;
      *)
        ZIP_PATH="$1"
        shift
        ;;
    esac
  done
}

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

setup_docker_command() {
  if [[ -n "$DOCKER_CMD" ]]; then
    if ! $DOCKER_CMD info >/dev/null 2>&1; then
      fail "cannot access Docker with DOCKER_CMD='$DOCKER_CMD'"
    fi
    return
  fi

  require_command docker
  if docker info >/dev/null 2>&1; then
    DOCKER_CMD="docker"
    return
  fi

  if command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    DOCKER_CMD="sudo docker"
    return
  fi

  fail "cannot access Docker daemon. Run with sudo, set DOCKER_CMD='sudo docker', or add user '$USER' to the docker group."
}

sync_from_zip() {
  [[ -f "$ZIP_PATH" ]] || fail "zip file not found: $ZIP_PATH"
  local unpack_dir extracted_root

  unpack_dir="$(mktemp -d /tmp/leek-trader-deploy.XXXXXX)"
  trap 'rm -rf "$unpack_dir"' RETURN

  mkdir -p "$WORK_DIR"
  unzip -q "$ZIP_PATH" -d "$unpack_dir"

  if [[ -f "$unpack_dir/Dockerfile.all-in-one" ]]; then
    extracted_root="$unpack_dir"
  else
    extracted_root="$(find "$unpack_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    [[ -n "$extracted_root" ]] || fail "zip did not contain a project directory"
  fi

  if [[ ! -f "$extracted_root/Dockerfile.all-in-one" ]]; then
    fail "Dockerfile.all-in-one not found inside extracted zip"
  fi

  shopt -s dotglob nullglob
  rm -rf "$WORK_DIR"/*
  cp -a "$extracted_root"/* "$WORK_DIR"/
  shopt -u dotglob nullglob
}

check_ports() {
  local port
  for port in "$HTTP_PORT" "$POSTGRES_PORT"; do
    if $DOCKER_CMD ps --format '{{.Names}} {{.Ports}}' | grep -v "^${APP_NAME} " | grep -q ":${port}->"; then
      fail "host port ${port} is already used by another Docker container. Override with HTTP_PORT or POSTGRES_PORT."
    fi
  done
}

build_frontend() {
  if [[ "$SKIP_FRONTEND_BUILD" == "1" ]]; then
    [[ -d "$WORK_DIR/frontend/dist" ]] || fail "SKIP_FRONTEND_BUILD=1 but frontend/dist does not exist."
    log "skipping frontend build"
    return
  fi

  local frontend_build_dir
  frontend_build_dir="$(mktemp -d /tmp/leek-trader-frontend.XXXXXX)"
  trap 'rm -rf "$frontend_build_dir"' RETURN

  mkdir -p "$frontend_build_dir"
  tar -C "$WORK_DIR/frontend" --exclude='./node_modules' --exclude='./dist' -cf - . | tar -C "$frontend_build_dir" -xf -
  mkdir -p "$frontend_build_dir/npm-cache"

  local node_major=0
  if command -v node >/dev/null 2>&1; then
    node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  fi

  if command -v npm >/dev/null 2>&1 && [[ "$node_major" -ge 18 ]]; then
    log "installing frontend dependencies"
    npm --prefix "$frontend_build_dir" ci --cache "$frontend_build_dir/npm-cache"
    log "building frontend assets"
    npm --prefix "$frontend_build_dir" run build
  else
    if [[ "$node_major" -gt 0 && "$node_major" -lt 18 ]]; then
      log "local Node.js is v${node_major}; building frontend with node:20-alpine Docker image"
    else
      log "npm not found; building frontend with node:20-alpine Docker image"
    fi
    $DOCKER_CMD run --rm \
      -u "$(id -u):$(id -g)" \
      -e HOME=/tmp \
      -e npm_config_cache=/tmp/npm-cache \
      -v "$frontend_build_dir:/app" \
      -w /app \
      node:20-alpine \
      sh -c 'npm ci --cache /tmp/npm-cache && npm run build'
  fi

  rm -rf "$WORK_DIR/frontend/dist"
  mkdir -p "$WORK_DIR/frontend/dist"
  cp -a "$frontend_build_dir/dist/." "$WORK_DIR/frontend/dist/"
}

build_image() {
  local image_exists=0
  local build_args=()
  if $DOCKER_CMD image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    image_exists=1
  fi

  if [[ -n "$APT_MIRROR" ]]; then
    build_args+=(--build-arg "APT_MIRROR=$APT_MIRROR")
  fi
  if [[ -n "$APT_SECURITY_MIRROR" ]]; then
    build_args+=(--build-arg "APT_SECURITY_MIRROR=$APT_SECURITY_MIRROR")
  fi
  if [[ -n "$PIP_INDEX_URL" ]]; then
    build_args+=(--build-arg "PIP_INDEX_URL=$PIP_INDEX_URL")
  fi
  if [[ "$INSTALL_RL_DEPS" == "1" || "$INSTALL_RL_DEPS" == "true" || "$INSTALL_RL_DEPS" == "yes" ]]; then
    build_args+=(--build-arg "INSTALL_RL_DEPS=1")
  fi

  if [[ "$REBUILD_IMAGE" == "1" || "$REBUILD_IMAGE" == "true" || "$REBUILD_IMAGE" == "yes" ]]; then
    log "building Docker image $IMAGE_NAME"
    $DOCKER_CMD build "${build_args[@]}" -f "$WORK_DIR/Dockerfile.all-in-one" -t "$IMAGE_NAME" "$WORK_DIR"
    return
  fi

  [[ "$image_exists" == "1" ]] || fail "image $IMAGE_NAME does not exist and REBUILD_IMAGE is not enabled. Run once with REBUILD_IMAGE=1 to create it."
  log "using existing Docker image $IMAGE_NAME"
}

restart_container() {
  log "stopping old container if present"
  $DOCKER_CMD rm -f "$APP_NAME" >/dev/null 2>&1 || true

  log "starting container $APP_NAME"
  $DOCKER_CMD run -d \
    --name "$APP_NAME" \
    --restart unless-stopped \
    -p "${HTTP_PORT}:80" \
    -p "${POSTGRES_PORT}:5432" \
    -v "$WORK_DIR/backend:/app/backend" \
    -v "$WORK_DIR/frontend/dist:/app/frontend/dist" \
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

  $DOCKER_CMD logs --tail 120 "$APP_NAME" >&2 || true
  fail "container did not become healthy at ${url}"
}

main() {
  parse_args "$@"

  require_command curl
  require_command unzip
  setup_docker_command

  sync_from_zip
  check_ports
  build_frontend
  build_image
  restart_container
  wait_for_health

  cat <<MSG

Deploy complete.
Zip source: $ZIP_PATH
Working dir: $WORK_DIR
Frontend:    http://127.0.0.1:${HTTP_PORT}
Backend:     http://127.0.0.1:${HTTP_PORT}/health
API docs:    http://127.0.0.1:${HTTP_PORT}/docs
PostgreSQL:  127.0.0.1:${POSTGRES_PORT} db=${POSTGRES_DB} user=${POSTGRES_USER}
Logs:        $DOCKER_CMD logs -f ${APP_NAME}

Update flow:
  1) Replace /home/diaoff/leek-trader-dev.zip with the new zip
  2) Run ./deploy-centos-all-in-one.sh again
  3) Use REBUILD_IMAGE=1 when Dockerfile or backend deps changed
MSG
}

main "$@"

#!/usr/bin/env bash

set -Eeuo pipefail

APP_NAME="${APP_NAME:-leek-trader}"
ZIP_PATH="${ZIP_PATH:-/home/diaoff/leek-trader-dev.zip}"
WORK_DIR="${WORK_DIR:-/home/diaoff/leek-trader}"
DOCKER_CMD="${DOCKER_CMD:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<EOF_USAGE
Usage: $0 [zip_path]
       $0 --zip /path/to/leek-trader-dev.zip

Update the existing container without rebuilding the image.
EOF_USAGE
}

log() {
  printf '[update] %s\n' "$*"
}

fail() {
  printf '[update] Error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command '$1'. Please install it first."
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

container_env_value() {
  local key="$1"
  $DOCKER_CMD inspect "$APP_NAME" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E "^${key}=" | head -n1 | cut -d= -f2- || true
}

container_port_value() {
  local container_port="$1"
  $DOCKER_CMD inspect "$APP_NAME" --format "{{(index (index .NetworkSettings.Ports \"${container_port}/tcp\") 0).HostPort}}" 2>/dev/null || true
}

container_volume_name() {
  local destination="$1"
  $DOCKER_CMD inspect "$APP_NAME" --format '{{range .Mounts}}{{if eq .Destination "'"$destination"'"}}{{.Name}}{{end}}{{end}}' | head -n1
}

ensure_container_exists() {
  if ! $DOCKER_CMD inspect "$APP_NAME" >/dev/null 2>&1; then
    fail "existing container '$APP_NAME' not found. Run deploy-centos-all-in-one.sh first."
  fi
}

main() {
  parse_args "$@"
  require_command unzip
  require_command curl
  setup_docker_command
  ensure_container_exists

  local postgres_db postgres_user postgres_password http_port postgres_port image_name pg_volume
  postgres_db="$(container_env_value POSTGRES_DB)"
  postgres_user="$(container_env_value POSTGRES_USER)"
  postgres_password="$(container_env_value POSTGRES_PASSWORD)"
  image_name="$($DOCKER_CMD inspect "$APP_NAME" --format '{{.Config.Image}}')"
  http_port="$(container_port_value 80)"
  postgres_port="$(container_port_value 5432)"
  pg_volume="$(container_volume_name /var/lib/postgresql/data)"

  [[ -n "$postgres_db" ]] || fail "failed to read POSTGRES_DB from existing container"
  [[ -n "$postgres_user" ]] || fail "failed to read POSTGRES_USER from existing container"
  [[ -n "$postgres_password" ]] || fail "failed to read POSTGRES_PASSWORD from existing container"
  [[ -n "$image_name" ]] || fail "failed to read image name from existing container"
  [[ -n "$http_port" ]] || http_port="10086"
  [[ -n "$postgres_port" ]] || postgres_port="5432"
  [[ -n "$pg_volume" ]] || fail "failed to read PostgreSQL volume from existing container"

  log "using existing container config: image=$image_name http_port=$http_port postgres_port=$postgres_port volume=$pg_volume"
  exec env \
    APP_NAME="$APP_NAME" \
    ZIP_PATH="$ZIP_PATH" \
    WORK_DIR="$WORK_DIR" \
    HTTP_PORT="$http_port" \
    POSTGRES_PORT="$postgres_port" \
    POSTGRES_DB="$postgres_db" \
    POSTGRES_USER="$postgres_user" \
    POSTGRES_PASSWORD="$postgres_password" \
    PG_VOLUME="$pg_volume" \
    IMAGE_NAME="$image_name" \
    REBUILD_IMAGE=0 \
    DOCKER_CMD="$DOCKER_CMD" \
    "$ROOT_DIR/deploy-centos-all-in-one.sh" "$ZIP_PATH"
}

main "$@"

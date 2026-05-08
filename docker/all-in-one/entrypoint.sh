#!/usr/bin/env bash
set -Eeuo pipefail

export APP_ENV="${APP_ENV:-production}"
export API_PREFIX="${API_PREFIX:-/api/v1}"
export POSTGRES_DB="${POSTGRES_DB:-leek_trader}"
export POSTGRES_USER="${POSTGRES_USER:-postgres}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
export PGDATA="${PGDATA:-/var/lib/postgresql/data}"
urlencode() {
  python3 -c 'from urllib.parse import quote; import sys; print(quote(sys.argv[1], safe=""))' "$1"
}

POSTGRES_USER_URL="$(urlencode "$POSTGRES_USER")"
POSTGRES_PASSWORD_URL="$(urlencode "$POSTGRES_PASSWORD")"
POSTGRES_DB_URL="$(urlencode "$POSTGRES_DB")"
export DATABASE_URL="postgresql+psycopg://${POSTGRES_USER_URL}:${POSTGRES_PASSWORD_URL}@127.0.0.1:5432/${POSTGRES_DB_URL}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export CELERY_BROKER_URL="${CELERY_BROKER_URL:-$REDIS_URL}"
export CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND:-$REDIS_URL}"

POSTGRES_BIN_FILE="$(find /usr/lib/postgresql -type f -name postgres -print -quit)"
POSTGRES_BIN_DIR="${POSTGRES_BIN_FILE%/postgres}"
if [[ -z "$POSTGRES_BIN_DIR" || "$POSTGRES_BIN_DIR" == "$POSTGRES_BIN_FILE" ]]; then
  POSTGRES_BIN_FILE="$(command -v postgres || true)"
  POSTGRES_BIN_DIR="${POSTGRES_BIN_FILE%/postgres}"
fi
if [[ -z "$POSTGRES_BIN_DIR" || "$POSTGRES_BIN_DIR" == "$POSTGRES_BIN_FILE" ]]; then
  echo '[all-in-one] Error: unable to locate postgres binary' >&2
  exit 1
fi
export PATH="$POSTGRES_BIN_DIR:$PATH"

pids=()

log() {
  printf '[all-in-one] %s\n' "$*"
}

shutdown() {
  log "stopping services"
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  if [[ -f "$PGDATA/postmaster.pid" ]]; then
    gosu postgres pg_ctl -D "$PGDATA" -m fast -w stop >/dev/null 2>&1 || true
  fi
}
trap shutdown EXIT INT TERM

initialize_postgres() {
  mkdir -p "$PGDATA" /var/run/postgresql
  chown -R postgres:postgres "$PGDATA" /var/run/postgresql
  chmod 700 "$PGDATA"

  if [[ ! -s "$PGDATA/PG_VERSION" ]]; then
    log "initializing PostgreSQL data directory"
    gosu postgres initdb -D "$PGDATA" --encoding=UTF8 --locale=C.UTF-8 --username=postgres
    {
      printf "listen_addresses = '*'\n"
      printf "port = 5432\n"
    } >> "$PGDATA/postgresql.conf"
    {
      printf 'host all all 127.0.0.1/32 scram-sha-256\n'
      printf 'host all all ::1/128 scram-sha-256\n'
      printf 'host all all 0.0.0.0/0 scram-sha-256\n'
    } >> "$PGDATA/pg_hba.conf"
  fi

  if grep -q "^listen_addresses" "$PGDATA/postgresql.conf"; then
    sed -i "s/^listen_addresses.*/listen_addresses = '*'/" "$PGDATA/postgresql.conf"
  else
    printf "listen_addresses = '*'\n" >> "$PGDATA/postgresql.conf"
  fi

  if ! grep -qF 'host all all 0.0.0.0/0 scram-sha-256' "$PGDATA/pg_hba.conf"; then
    printf 'host all all 0.0.0.0/0 scram-sha-256\n' >> "$PGDATA/pg_hba.conf"
  fi
}

start_postgres() {
  initialize_postgres
  log "starting PostgreSQL"
    gosu postgres pg_ctl -D "$PGDATA" -l "$PGDATA/postgres.log" -w start

  if [[ "$POSTGRES_USER" == "postgres" ]]; then
    gosu postgres psql -v ON_ERROR_STOP=1 --username postgres --dbname postgres <<SQL
ALTER USER postgres WITH PASSWORD '${POSTGRES_PASSWORD}';
SELECT 'CREATE DATABASE ${POSTGRES_DB}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${POSTGRES_DB}')\gexec
SQL
  else
    gosu postgres psql -v ON_ERROR_STOP=1 --username postgres --dbname postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${POSTGRES_USER}') THEN
    CREATE ROLE ${POSTGRES_USER} LOGIN PASSWORD '${POSTGRES_PASSWORD}';
  ELSE
    ALTER ROLE ${POSTGRES_USER} WITH LOGIN PASSWORD '${POSTGRES_PASSWORD}';
  END IF;
END
\$\$;
SELECT 'CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${POSTGRES_DB}')\gexec
SQL
  fi
}

start_redis() {
  log "starting Redis"
  redis-server --bind 127.0.0.1 --port 6379 --save "" --appendonly no &
  pids+=("$!")
}

start_backend() {
  log "starting FastAPI backend"
  cd /app/backend
  uvicorn app.main:app --host 127.0.0.1 --port 8000 &
  pids+=("$!")
}

start_celery() {
  log "starting Celery worker and beat"
  cd /app/backend
  celery -A app.core.celery_app.celery_app worker --loglevel=info --pool="${CELERY_WORKER_POOL:-solo}" --concurrency="${CELERY_WORKER_CONCURRENCY:-1}" &
  pids+=("$!")
  celery -A app.core.celery_app.celery_app beat --loglevel=info &
  pids+=("$!")
}

start_nginx() {
  log "starting nginx"
  nginx -g 'daemon off;' &
  pids+=("$!")
}

start_postgres
start_redis
start_backend
start_celery
start_nginx

log "ready on http://0.0.0.0:80"
wait -n "${pids[@]}"

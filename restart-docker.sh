#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    echo "Error: neither 'docker compose' nor 'docker-compose' is available." >&2
    exit 1
  fi
}

echo "Restarting Leek Trader Docker services..."
compose_cmd down
compose_cmd up -d --build "$@"

cat <<'EOF'
Leek Trader has restarted.
Frontend: http://localhost:5173
Backend:  http://localhost:8000
EOF

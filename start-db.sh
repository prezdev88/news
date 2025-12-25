#!/usr/bin/env bash
set -euo pipefail

main() {
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "$script_dir"

  echo "Starting PostgreSQL (db)..."
  docker compose up -d db
  echo "Waiting for PostgreSQL health..."
  if ! docker compose ps --status running db >/dev/null 2>&1; then
    echo "PostgreSQL container is not running."
    exit 1
  fi
  for i in {1..20}; do
    status="$(docker inspect -f '{{.State.Health.Status}}' news-db 2>/dev/null || true)"
    if [ "$status" = "healthy" ]; then
      echo "PostgreSQL is healthy."
      return 0
    fi
    sleep 1
  done
  echo "PostgreSQL did not report healthy within 20s."
  exit 1
}

main "$@"

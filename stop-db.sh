#!/usr/bin/env bash
set -euo pipefail

main() {
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "$script_dir"

  echo "Stopping PostgreSQL (db)..."
  docker compose stop db
  echo "PostgreSQL stopped."
}

main "$@"

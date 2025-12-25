#!/usr/bin/env bash
set -euo pipefail

main() {
  # Ensure we run from the repo root (where docker-compose.yml lives)
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "$script_dir"

  echo "Building images (backend)..."
  COMPOSE_BAKE=0 DOCKER_BUILDKIT=0 docker compose build --no-cache backend

  echo "Starting stack..."
  docker compose up -d

  echo "Stack is up (no host ports published)."
  echo "Containers expose:"
  echo " - App:     8080 (internal)"
  echo " - Postgres:5432 (internal, user/pass/db: news/news/news)"
  echo "Use your Nginx reverse proxy to route traffic to the backend if needed."
}

main "$@"

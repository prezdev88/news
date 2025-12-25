#!/usr/bin/env bash
set -euo pipefail

main() {
  # Ensure we run from the repo root (where docker-compose.yml lives)
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "$script_dir"

  echo "Building images (news-backend/news-frontend)..."
  COMPOSE_BAKE=0 DOCKER_BUILDKIT=0 docker compose -f docker-compose.yml build --no-cache news-backend news-frontend

  echo "Starting stack..."
  docker compose -f docker-compose.yml up -d

  echo "Stack is up (no host ports published)."
  echo "Containers expose:"
  echo " - Backend: 8080 (internal)"
  echo " - Front:   80 (internal)"
  echo " - Postgres:5432 (internal, user/pass/db: news/news/news)"
  echo "Use your Nginx reverse proxy to route traffic to front/back if needed."
}

main "$@"

#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$task_root"
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  printf '%s\n' 'Se necesitan Docker y Docker Compose para ejecutar la versión alfa.' >&2
  exit 1
fi
if [[ ! -f "$task_root/config.json" ]]; then
  printf '%s\n' 'Falta config.json. Copia config.example.json a config.json y revisa sus valores.' >&2
  exit 1
fi
mkdir -p "$task_root/output"
export NEWS_UID="$(id -u)"
export NEWS_GID="$(id -g)"
docker compose -f "$task_root/compose.yaml" up -d --wait ollama
exec docker compose -f "$task_root/compose.yaml" run --build --rm -T news "$@"

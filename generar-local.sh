#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$task_root"
task_python="${MANANA_PYTHON:-python3}"
if [[ -x "$task_root/.venv/bin/python" ]]; then
  task_python="$task_root/.venv/bin/python"
fi
if ! "$task_python" -c 'import requests, bs4, feedparser, cairo' >/dev/null 2>&1; then
  printf '%s\n' 'Faltan dependencias. Ejecuta ./instalar.sh y vuelve a intentarlo.' >&2
  exit 1
fi
exec "$task_python" -m manana "$@"

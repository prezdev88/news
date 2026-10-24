#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$task_root"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
printf '%s\n' 'Dependencias locales listas. Ejecuta ./generar-local.sh o ./abrir-app.sh. La versión alfa dockerizada usa ./generar.sh.'

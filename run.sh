#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -x "$ROOT/.venv/bin/mini-metro-lab" || ! -d "$ROOT/.vendor/python_mini_metro/.git" ]]; then
  "$ROOT/scripts/bootstrap.sh"
fi

exec "$ROOT/.venv/bin/mini-metro-lab" "$@"

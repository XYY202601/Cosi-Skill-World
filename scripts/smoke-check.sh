#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stack-common.sh"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stack_load_env_defaults "$repo_root"
python_bin="$repo_root/.venv/bin/python"

if [[ ! -x "$python_bin" ]]; then
  python_bin="${PYTHON:-python3}"
fi

"$python_bin" "$repo_root/scripts/smoke_check.py" "$@"

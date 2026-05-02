#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stack-common.sh"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stack_load_env_defaults "$repo_root"
runtime_dir="$repo_root/apps/mr-visit-jp-runtime"
python_bin="$repo_root/.venv/bin/python"

if [[ ! -x "$python_bin" ]]; then
  python_bin="${PYTHON:-python3}"
fi

mode="${MR_RUNTIME_PERSISTENCE_MODE:-file}"
echo "[seed-mr-visit-jp] persistence_mode=${mode}"

export PYTHONPATH="$runtime_dir/src${PYTHONPATH:+:$PYTHONPATH}"

"$python_bin" -m seed_demo_data "$@"

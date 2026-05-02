#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stack-common.sh"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stack_load_env_defaults "$repo_root"
runtime_dir="$repo_root/apps/mr-visit-jp-runtime"
prompt_builder_dir="$repo_root/packages/prompt-builder/src"
evaluation_core_dir="$repo_root/packages/evaluation-core/src"
python_bin="$repo_root/.venv/bin/python"

if [[ ! -x "$python_bin" ]]; then
  python_bin="${PYTHON:-python3}"
fi

export PYTHONPATH="$runtime_dir/src:$prompt_builder_dir:$evaluation_core_dir${PYTHONPATH:+:$PYTHONPATH}"

"$python_bin" -m offline_evaluation_report "$@"

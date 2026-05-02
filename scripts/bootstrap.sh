#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

log() {
  echo "[bootstrap] $*"
}

require_command() {
  local command_name="$1"
  command -v "$command_name" >/dev/null || {
    log "missing required command: $command_name"
    exit 1
  }
}

require_command pnpm
require_command python3

python_bin="${PYTHON:-python3}"

log "verifying Python version..."
"$python_bin" - <<'PY'
import sys

major, minor = sys.version_info[:2]
if (major, minor) < (3, 11):
    raise SystemExit("Python 3.11+ is required")
PY

if [[ ! -f .env && -f .env.example ]]; then
  log "creating .env from .env.example"
  cp .env.example .env
fi

if [[ ! -x .venv/bin/python ]]; then
  log "creating .venv"
  "$python_bin" -m venv .venv
fi

venv_python="$repo_root/.venv/bin/python"

log "upgrading pip"
"$venv_python" -m pip install --upgrade pip

log "installing Python runtime packages"
"$venv_python" -m pip install \
  -e packages/skill-registry \
  -e packages/prompt-builder \
  -e apps/mr-visit-jp-runtime \
  -e apps/gp-visit-jp-runtime \
  -e apps/hermes-orchestrator

log "installing web dependencies"
pnpm install

log "seeding demo runtime data"
bash scripts/seed-mr-visit-jp.sh

log "done"
log "next: run 'make stack-up' or start MR runtime + GP runtime + Hermes + web manually, then run 'make smoke-check'"

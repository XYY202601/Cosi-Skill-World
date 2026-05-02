#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stack-common.sh"

repo_root="$(stack_repo_root)"
cd "$repo_root"

log() {
  echo "[stack-up] $*"
}

require_command() {
  local command_name="$1"
  command -v "$command_name" >/dev/null 2>&1 || {
    log "missing required command: $command_name"
    exit 1
  }
}

should_bootstrap=false
if [[ ! -x "$repo_root/.venv/bin/python" ]]; then
  should_bootstrap=true
fi
if [[ ! -d "$repo_root/node_modules" ]]; then
  should_bootstrap=true
fi
if [[ ! -f "$repo_root/.env" && -f "$repo_root/.env.example" ]]; then
  should_bootstrap=true
fi
if [[ -x "$repo_root/.venv/bin/python" ]]; then
  if ! "$repo_root/.venv/bin/python" - <<'PY' >/dev/null 2>&1; then
import importlib.metadata as metadata

metadata.version("mr-visit-jp-runtime")
metadata.version("gp-visit-jp-runtime")
metadata.version("hermes-orchestrator")
metadata.version("skill-registry")
metadata.version("prompt-builder")
PY
    should_bootstrap=true
  fi
fi

if [[ "$should_bootstrap" == "true" ]]; then
  log "bootstrap prerequisites missing, running bootstrap"
  bash "$repo_root/scripts/bootstrap.sh"
fi

stack_load_env_defaults "$repo_root"

require_command curl
require_command pnpm

: "${WEB_PORT:=3000}"
: "${HERMES_PORT:=8000}"
: "${MR_RUNTIME_PORT:=8100}"
: "${GP_RUNTIME_PORT:=8200}"
: "${WEB_HOST:=127.0.0.1}"
: "${HERMES_HOST:=127.0.0.1}"
: "${MR_RUNTIME_HOST:=127.0.0.1}"
: "${GP_RUNTIME_HOST:=127.0.0.1}"

state_dir="$(stack_state_dir "$repo_root")"
mkdir -p "$state_dir"

venv_python="$repo_root/.venv/bin/python"
web_base="http://127.0.0.1:$WEB_PORT"
hermes_base="http://127.0.0.1:$HERMES_PORT"
runtime_base="http://127.0.0.1:$MR_RUNTIME_PORT"
gp_runtime_base="http://127.0.0.1:$GP_RUNTIME_PORT"

started_services=()
startup_complete=false

resolve_runtime_health_mode() {
  local health_url="$1"
  local response
  response="$(curl -fsS --max-time 2 "$health_url" 2>/dev/null || true)"
  if [[ -z "$response" ]]; then
    return 1
  fi

  "$venv_python" - "$response" <<'PY'
import json
import sys

try:
    payload = json.loads(sys.argv[1])
except Exception:
    raise SystemExit(1)

mode = payload.get("persistence_mode")
if isinstance(mode, str) and mode.strip():
    print(mode.strip())
    raise SystemExit(0)

raise SystemExit(1)
PY
}

align_runtime_mode_if_needed() {
  local desired_mode
  local actual_mode
  desired_mode="$(printf '%s' "${MR_RUNTIME_PERSISTENCE_MODE:-file}" | tr '[:upper:]' '[:lower:]')"

  if ! stack_service_running "$state_dir" runtime; then
    return 0
  fi

  if ! actual_mode="$(resolve_runtime_health_mode "$runtime_base/healthz")"; then
    log "runtime mode check unavailable; continuing without alignment"
    return 0
  fi

  if [[ "$actual_mode" != "$desired_mode" ]]; then
    log "runtime mode mismatch detected running=$actual_mode desired=$desired_mode; restarting runtime"
    stack_stop_service "$state_dir" runtime || true
  fi
}

cleanup_on_error() {
  local exit_code="$?"
  if [[ "$startup_complete" == "true" || "$exit_code" -eq 0 ]]; then
    return 0
  fi

  log "startup failed, stopping partial stack"
  local index
  for ((index = ${#started_services[@]} - 1; index >= 0; index -= 1)); do
    stack_stop_service "$state_dir" "${started_services[$index]}" || true
  done
}
trap cleanup_on_error EXIT

align_runtime_mode_if_needed

ensure_port_available() {
  local service="$1"
  local port="$2"
  if ! stack_assert_port_available "$service" "$port" 2>/dev/null; then
    local message
    message="$(stack_port_conflict_message "$service" "$port")"
    log "$message"
    exit 1
  fi
}

start_service() {
  local service="$1"
  local port="$2"
  local health_url="$3"
  local workdir="$4"
  shift 4
  local -a command=("$@")
  local pid_file
  local log_file
  pid_file="$(stack_pid_file "$state_dir" "$service")"
  log_file="$(stack_log_file "$state_dir" "$service")"

  if stack_service_running "$state_dir" "$service"; then
    log "$service already running pid=$(stack_service_pid "$state_dir" "$service")"
    return 0
  fi

  ensure_port_available "$service" "$port"
  log "starting $service on port $port"
  nohup bash -lc '
    workdir="$1"
    shift
    cd "$workdir"
    exec "$@"
  ' bash "$workdir" "${command[@]}" >"$log_file" 2>&1 &

  local pid="$!"
  echo "$pid" > "$pid_file"

  if ! stack_wait_for_http "$health_url" 60; then
    log "$service failed to become ready; recent log:"
    tail -n 40 "$log_file" || true
    exit 1
  fi

  started_services+=("$service")
  log "$service ready at $health_url"
}

start_service \
  runtime \
  "$MR_RUNTIME_PORT" \
  "$runtime_base/healthz" \
  "$repo_root/apps/mr-visit-jp-runtime" \
  env \
  MR_RUNTIME_PORT="$MR_RUNTIME_PORT" \
  MR_RUNTIME_HOST="$MR_RUNTIME_HOST" \
  "$venv_python" \
  -m \
  uvicorn \
  main:app \
  --app-dir \
  src \
  --host \
  "$MR_RUNTIME_HOST" \
  --port \
  "$MR_RUNTIME_PORT"

start_service \
  gp-runtime \
  "$GP_RUNTIME_PORT" \
  "$gp_runtime_base/healthz" \
  "$repo_root/apps/gp-visit-jp-runtime" \
  env \
  GP_RUNTIME_PORT="$GP_RUNTIME_PORT" \
  GP_RUNTIME_HOST="$GP_RUNTIME_HOST" \
  "$venv_python" \
  -m \
  uvicorn \
  main:app \
  --app-dir \
  src \
  --host \
  "$GP_RUNTIME_HOST" \
  --port \
  "$GP_RUNTIME_PORT"

start_service \
  hermes \
  "$HERMES_PORT" \
  "$hermes_base/healthz" \
  "$repo_root/apps/hermes-orchestrator" \
  env \
  HERMES_PORT="$HERMES_PORT" \
  HERMES_HOST="$HERMES_HOST" \
  MR_VISIT_JP_RUNTIME_BASE="$runtime_base" \
  GP_VISIT_JP_RUNTIME_BASE="$gp_runtime_base" \
  "$venv_python" \
  -m \
  uvicorn \
  main:app \
  --app-dir \
  src \
  --host \
  "$HERMES_HOST" \
  --port \
  "$HERMES_PORT"

start_service \
  web \
  "$WEB_PORT" \
  "$web_base/api/local/diagnostics" \
  "$repo_root" \
  env \
  WEB_PORT="$WEB_PORT" \
  HERMES_API_BASE="$hermes_base" \
  MR_VISIT_JP_RUNTIME_BASE="$runtime_base" \
  NEXT_TELEMETRY_DISABLED=1 \
  pnpm \
  --filter \
  web \
  exec \
  next \
  dev \
  --hostname \
  "$WEB_HOST" \
  --port \
  "$WEB_PORT"

startup_complete=true
trap - EXIT

log "stack is ready"
log "web: $web_base"
log "Hermes: $hermes_base"
log "MR runtime: $runtime_base"
log "GP runtime: $gp_runtime_base"
log "logs: $state_dir"
log "next: run 'make smoke-check' or 'make stack-status'"

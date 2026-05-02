#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stack-common.sh"

repo_root="$(stack_repo_root)"
stack_load_env_defaults "$repo_root"

: "${WEB_PORT:=3000}"
: "${HERMES_PORT:=8000}"
: "${MR_RUNTIME_PORT:=8100}"
: "${GP_RUNTIME_PORT:=8200}"

state_dir="$(stack_state_dir "$repo_root")"
runtime_health_url="http://127.0.0.1:$MR_RUNTIME_PORT/healthz"
runtime_diagnostics_url="http://127.0.0.1:$MR_RUNTIME_PORT/_local/diagnostics"
gp_runtime_health_url="http://127.0.0.1:$GP_RUNTIME_PORT/healthz"
gp_runtime_diagnostics_url="http://127.0.0.1:$GP_RUNTIME_PORT/v1/scenarios"
hermes_health_url="http://127.0.0.1:$HERMES_PORT/healthz"
hermes_diagnostics_url="http://127.0.0.1:$HERMES_PORT/_local/diagnostics"
web_health_url="http://127.0.0.1:$WEB_PORT/api/healthz"
web_diagnostics_url="http://127.0.0.1:$WEB_PORT/api/runtime/scenarios"

service_health_url() {
  local service="$1"
  case "$service" in
    runtime) echo "$runtime_health_url" ;;
    gp-runtime) echo "$gp_runtime_health_url" ;;
    hermes) echo "$hermes_health_url" ;;
    web) echo "$web_health_url" ;;
  esac
}

service_diagnostics_url() {
  local service="$1"
  case "$service" in
    runtime) echo "$runtime_diagnostics_url" ;;
    gp-runtime) echo "$gp_runtime_diagnostics_url" ;;
    hermes) echo "$hermes_diagnostics_url" ;;
    web) echo "$web_diagnostics_url" ;;
  esac
}

print_http_snapshot() {
  local service="$1"
  local label="$2"
  local url="$3"
  local response

  if ! command -v curl >/dev/null 2>&1; then
    echo "[stack-status] $service $label=unavailable reason=curl-not-installed url=$url"
    return
  fi

  if response="$(curl -fsS --max-time 2 "$url" 2>/dev/null)"; then
    echo "[stack-status] $service $label=$response"
  else
    echo "[stack-status] $service $label=unavailable url=$url"
  fi
}

print_recent_log() {
  local service="$1"
  local log_file="$2"
  local recent_line

  if [[ ! -f "$log_file" ]]; then
    return
  fi

  recent_line="$(tail -n 5 "$log_file" 2>/dev/null | sed -n '/./p' | tail -n 1)"
  if [[ -n "$recent_line" ]]; then
    echo "[stack-status] $service recent_log=$recent_line"
  fi
}

print_service_status() {
  local service="$1"
  local port="$2"
  local pid
  local log_file
  local health_url
  local diagnostics_url
  pid="$(stack_service_pid "$state_dir" "$service")"
  log_file="$(stack_log_file "$state_dir" "$service")"
  health_url="$(service_health_url "$service")"
  diagnostics_url="$(service_diagnostics_url "$service")"

  if stack_is_pid_running "$pid"; then
    echo "[stack-status] $service running pid=$pid port=$port log=$log_file health_url=$health_url diagnostics_url=$diagnostics_url"
    print_http_snapshot "$service" "health" "$health_url"
    print_http_snapshot "$service" "diagnostics" "$diagnostics_url"
    print_recent_log "$service" "$log_file"
  else
    echo "[stack-status] $service stopped port=$port log=$log_file health_url=$health_url diagnostics_url=$diagnostics_url"
  fi
}

echo "[stack-status] state_dir=$state_dir"
print_service_status runtime "$MR_RUNTIME_PORT"
print_service_status gp-runtime "$GP_RUNTIME_PORT"
print_service_status hermes "$HERMES_PORT"
print_service_status web "$WEB_PORT"

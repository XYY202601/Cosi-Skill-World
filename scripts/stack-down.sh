#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stack-common.sh"

repo_root="$(stack_repo_root)"
stack_load_env_defaults "$repo_root"
state_dir="$(stack_state_dir "$repo_root")"

log() {
  echo "[stack-down] $*"
}

if [[ ! -d "$state_dir" ]]; then
  log "stack state directory not found: $state_dir"
  exit 0
fi

for service in web hermes gp-runtime runtime; do
  if stack_service_running "$state_dir" "$service"; then
    log "stopping $service pid=$(stack_service_pid "$state_dir" "$service")"
  else
    log "$service not running"
  fi
  stack_stop_service "$state_dir" "$service"
done

log "stack stopped"
log "logs retained at $state_dir"

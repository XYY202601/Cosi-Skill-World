#!/usr/bin/env bash

stack_repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

stack_load_env_defaults() {
  local repo_root="$1"
  local env_file="$repo_root/.env"

  if [[ ! -f "$env_file" ]]; then
    return 0
  fi

  while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
    local line="$raw_line"
    line="${line%$'\r'}"
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" != *=* ]] && continue

    local key="${line%%=*}"
    local value="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    [[ -z "$key" ]] && continue

    if [[ -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  done < "$env_file"
}

stack_state_dir() {
  local repo_root="$1"
  echo "${STACK_STATE_DIR:-$repo_root/.tmp/local-stack}"
}

stack_pid_file() {
  local state_dir="$1"
  local service="$2"
  echo "$state_dir/$service.pid"
}

stack_log_file() {
  local state_dir="$1"
  local service="$2"
  echo "$state_dir/$service.log"
}

stack_is_pid_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

stack_cleanup_stale_pid() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return 0
  fi

  local pid
  pid="$(<"$pid_file")"
  if ! stack_is_pid_running "$pid"; then
    rm -f "$pid_file"
  fi
}

stack_service_pid() {
  local state_dir="$1"
  local service="$2"
  local pid_file
  pid_file="$(stack_pid_file "$state_dir" "$service")"
  stack_cleanup_stale_pid "$pid_file"
  if [[ -f "$pid_file" ]]; then
    cat "$pid_file"
  fi
}

stack_service_running() {
  local state_dir="$1"
  local service="$2"
  local pid
  pid="$(stack_service_pid "$state_dir" "$service")"
  stack_is_pid_running "$pid"
}

stack_port_pids() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u
    return
  fi

  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "( sport = :$port )" 2>/dev/null \
      | awk -F'pid=' 'NR > 1 && NF > 1 {split($2, parts, ","); print parts[1]}' \
      | sort -u
  fi
}

stack_port_in_use() {
  local port="$1"
  [[ -n "$(stack_port_pids "$port")" ]]
}

stack_port_conflict_message() {
  local service="$1"
  local port="$2"
  local pids
  pids="$(stack_port_pids "$port" | tr '\n' ' ')"
  echo "$service port $port is already in use by pid(s): ${pids:-unknown}"
}

stack_assert_port_available() {
  local service="$1"
  local port="$2"
  if stack_port_in_use "$port"; then
    echo "$(stack_port_conflict_message "$service" "$port")" >&2
    return 1
  fi
}

stack_wait_for_http() {
  local url="$1"
  local timeout_seconds="${2:-60}"
  local attempt

  for ((attempt = 0; attempt < timeout_seconds; attempt += 1)); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  return 1
}

stack_stop_service() {
  local state_dir="$1"
  local service="$2"
  local pid_file
  pid_file="$(stack_pid_file "$state_dir" "$service")"
  stack_cleanup_stale_pid "$pid_file"

  if [[ ! -f "$pid_file" ]]; then
    return 0
  fi

  local pid
  pid="$(<"$pid_file")"
  if stack_is_pid_running "$pid"; then
    kill "$pid" >/dev/null 2>&1 || true
    local attempt
    for ((attempt = 0; attempt < 20; attempt += 1)); do
      if ! stack_is_pid_running "$pid"; then
        break
      fi
      sleep 1
    done
  fi

  if stack_is_pid_running "$pid"; then
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi

  rm -f "$pid_file"
}

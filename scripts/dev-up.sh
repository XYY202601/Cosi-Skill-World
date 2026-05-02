#!/usr/bin/env bash
set -euo pipefail

docker compose up -d postgres redis
echo "[dev-up] postgres + redis are up"

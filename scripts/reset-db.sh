#!/usr/bin/env bash
set -euo pipefail

: "${POSTGRES_USER:=cosi}"
: "${POSTGRES_DB:=cosi}"

docker compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS $POSTGRES_DB;"
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE $POSTGRES_DB;"

echo "[reset-db] database reset complete"

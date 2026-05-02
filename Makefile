SHELL := /bin/bash
FORMAT ?= text

.PHONY: bootstrap dev-up dev-down doctor validate-content reset-db seed-mr-visit-jp seed-training-data migrate-runtime-sql import-runtime-sql smoke-check stack-up stack-down stack-status check-no-reference-imports evaluate-mr-visit-jp-fixtures export-human-review-fixture-candidates dev-up-sql-stack test-sql test-sql-only

bootstrap:
	bash scripts/bootstrap.sh

dev-up:
	bash scripts/dev-up.sh

dev-down:
	bash scripts/dev-down.sh

doctor:
	bash scripts/doctor.sh

validate-content:
	bash scripts/validate-content.sh

evaluate-mr-visit-jp-fixtures:
	bash scripts/evaluate-mr-visit-jp-fixtures.sh --format $(FORMAT)

export-human-review-fixture-candidates:
	bash scripts/export-human-review-fixture-candidates.sh

reset-db:
	bash scripts/reset-db.sh

seed-mr-visit-jp:
	bash scripts/seed-mr-visit-jp.sh

seed-training-data:
	bash scripts/seed-training-data.sh

migrate-runtime-sql:
	.venv/bin/alembic -c apps/mr-visit-jp-runtime/alembic.ini upgrade head

import-runtime-sql:
	bash scripts/import-runtime-sql.sh

smoke-check:
	bash scripts/smoke-check.sh

stack-up:
	bash scripts/stack-up.sh

stack-down:
	bash scripts/stack-down.sh

stack-status:
	bash scripts/stack-status.sh

check-no-reference-imports:
	bash scripts/check-no-reference-imports.sh

# ── PostgreSQL first-class mode ─────────────────────────────────────────

dev-up-sql-stack:
	@echo "=== Starting PostgreSQL ==="
	docker compose up -d postgres
	@echo "=== Waiting for PostgreSQL ==="
	@until docker compose exec -T postgres pg_isready -U cosi 2>/dev/null; do sleep 1; done
	@echo "=== Running Alembic migrations ==="
	.venv/bin/alembic -c apps/mr-visit-jp-runtime/alembic.ini upgrade head
	@echo "=== Seeding demo data (SQL mode) ==="
	MR_RUNTIME_PERSISTENCE_MODE=sql bash scripts/seed-mr-visit-jp.sh
	@echo "=== Starting stack (SQL mode) ==="
	MR_RUNTIME_PERSISTENCE_MODE=sql bash scripts/stack-up.sh
	@echo "=== Ready. Run: make smoke-check ==="

test-sql:
	@echo "=== Running full test suite in SQL mode ==="
	MR_RUNTIME_PERSISTENCE_MODE=sql ./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests

test-sql-only:
	@echo "=== Running API tests in SQL mode ==="
	MR_RUNTIME_PERSISTENCE_MODE=sql ./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_runtime_api.py -v

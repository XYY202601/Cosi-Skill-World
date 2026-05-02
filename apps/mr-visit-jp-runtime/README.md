# mr-visit-jp-runtime

Domain runtime for Japanese MR visit training.

## Purpose

This service owns the full training loop for the first domain:
- session lifecycle
- scenario loading
- doctor roleplay
- session direction
- scoring
- diagnosis
- coaching feedback
- compliance tagging
- progression update

## Domain Goal

Train users to perform high-quality, compliant, professional MR visits in Japanese.

This is not generic sales training.
This is structured MR visit training.

## Core Runtime Components

- Session Engine
- Scenario Engine
- Doctor Agent
- Director Agent
- Judge Agent
- Coach Agent
- Compliance Checker

## Responsibilities

- create and manage session state
- load scenario templates
- run turn-by-turn dialogue logic
- persist transcript and events
- score 7 subskills
- generate structured diagnosis
- generate coaching feedback
- update learner progression
- suggest next scenarios

## Output Contracts

- review payload
- diagnosis payload
- compliance flags
- progression delta
- recommendation payload

## Current Version

Alpha:
- text only
- single-user
- fixed 8 scenario set
- no voice
- no hospital world simulation

## Runtime Storage

- Session, event, and learner-progress artifacts are persisted to local files.
- Default data directory: `apps/mr-visit-jp-runtime/.data/`
- Override with environment variable: `MR_RUNTIME_DATA_DIR=/absolute/path`
- Runtime persistence mode defaults to `file`.
- Set `MR_RUNTIME_PERSISTENCE_MODE=sql` to use the PostgreSQL-backed store adapters.
- Override the runtime DB URL with `MR_RUNTIME_SQLALCHEMY_URL=postgresql+psycopg://...`.
- Demo seed-on-boot behavior is controlled by `MR_RUNTIME_DEMO_SEED_MODE=auto|manual|disabled`.
- The default local setup uses `manual`, and `make bootstrap` / `make seed-mr-visit-jp` perform the explicit seed step.
- You can also seed or refresh them manually from the repo root with `make seed-mr-visit-jp`.
- `make seed-mr-visit-jp -- --list-learners` lists the built-in demo learner ids.
- `make seed-mr-visit-jp -- --append-today-sessions 25 --append-today-learner-id learner_demo_001` appends a same-day, mixed-case batch to the default demo learner.
- `make seed-training-data` seeds comprehensive SQL-backed training data for `learner_A`, `learner_B`, and `learner_C`.
- `bash scripts/seed-training-data.sh --sessions-per-learner 24 --min-turns 5 --max-turns 10 --truncate-sql-first` reseeds A/B/C with full-spectrum sessions while enforcing 5-10 turns per session.
- `seed-training-data` now aborts by default when the currently running runtime reports a different `persistence_mode` than the seed target, to prevent “seeded but not visible in UI” mismatches.
- PostgreSQL-targeted Alembic scaffolding now exists under `apps/mr-visit-jp-runtime/alembic/`.
- From the repo root, generate offline SQL with:
  - `.venv/bin/alembic -c apps/mr-visit-jp-runtime/alembic.ini upgrade head --sql`
- Apply the base schema against the configured database with:
  - `.venv/bin/alembic -c apps/mr-visit-jp-runtime/alembic.ini upgrade head`
- Import file-backed runtime data into SQL with:
  - `make import-runtime-sql -- --dry-run`
  - `make import-runtime-sql -- --apply`
  - `make import-runtime-sql -- --apply --truncate-first`
- The importer validates session/event/progress artifacts before writing to SQL.
- Invalid artifacts abort `--apply`; orphan event files are reported and skipped.

## SQL Mode Local Path

From the repo root, the end-to-end SQL persistence flow is:

```bash
# 1. Start PostgreSQL
docker compose up -d postgres

# 2. Run Alembic migration to create schema
make migrate-runtime-sql

# 3. Seed demo data (creates file-mode data first, then imports to SQL)
make seed-mr-visit-jp -- --apply
# Or import existing file data into SQL:
# make import-runtime-sql -- --apply

# 4. Start the runtime in SQL mode
MR_RUNTIME_PERSISTENCE_MODE=sql \
  MR_RUNTIME_SQLALCHEMY_URL=postgresql+psycopg://cosi:cosi@127.0.0.1:5439/cosi \
  .venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8100

# 5. Run smoke check against SQL-backed runtime
MR_RUNTIME_PERSISTENCE_MODE=sql \
  MR_VISIT_JP_RUNTIME_BASE=http://127.0.0.1:8100 \
  .venv/bin/python scripts/smoke_check.py --runtime-base http://127.0.0.1:8100
```

Or use the existing `make stack-up` with file mode, then switch to SQL mode independently.

`/healthz` reports `persistence_mode` so you can verify which mode is active:
```bash
curl -s http://127.0.0.1:8100/healthz | python -m json.tool
# → {"status":"ok", "persistence_mode":"sql", ...}
```

## Artifact Generation Mode

- `MR_RUNTIME_MODEL_MODE=mock` (default): use deterministic model-like structured outputs.
- `MR_RUNTIME_MODEL_MODE=openai_compat`: call OpenAI-compatible `/chat/completions`.
- `MR_RUNTIME_MODEL_MODE=disabled`: skip model attempt and use rule fallback only.
- `MR_RUNTIME_MODEL_TIMEOUT_SEC` controls provider request timeout in seconds for `openai_compat`.
- `MR_RUNTIME_MODEL_MAX_RETRIES` controls retry count after the first attempt for retryable provider failures.
- `MR_RUNTIME_MODEL_RETRY_BACKOFF_SEC` controls fixed sleep between retry attempts.
- Retryable HTTP failures respect provider `Retry-After` when present.
- In `openai_compat` mode, prompt contracts are loaded from:
  - `domains/mr_visit_jp/prompts/judge/openai_compat.yaml`
  - `domains/mr_visit_jp/prompts/coach/openai_compat.yaml`
  - `domains/mr_visit_jp/prompts/compliance/openai_compat.yaml`
- Review metadata now distinguishes:
  - `artifact_sources`: whether judge/coach/compliance came from generated artifacts or rule fallback
  - `artifact_modes`: whether generated artifacts were from `model` or `mock`, or ended up as `rule`
  - `model_meta`: provider attempt count, request id, failure stage, and fallback target when generation fails

## Prompt Profiles And Experiments

- Prompt profiles are declared in `domains/mr_visit_jp/prompts/openai_compat_profiles.yaml`.
- Runtime defaults to `MR_RUNTIME_PROMPT_PROFILE=alpha_baseline_v1`.
- Optional flags:
  - `MR_RUNTIME_EXPERIMENT_ID` for a named rollout or canary id.
- `MR_RUNTIME_EXPERIMENT_FLAGS` for comma-separated feature/experiment tags.
- New-session rollout now uses gate enforcement, not report-only status:
  - the stable registry default profile remains the fallback rollout target
  - a non-default profile or explicit experiment id must pass offline and online gates before it becomes the active runtime prompt context
  - blocked rollout requests fall back to the stable profile unless `MR_RUNTIME_ALLOW_BLOCKED_PROMPT_ROLLOUT=1` is set explicitly for canary sampling
- The selected prompt profile and contract versions are frozen when a session starts.
- Review payloads, session events, and persisted session files retain that frozen prompt context so restarted sessions do not drift to newer runtime defaults.

## Evaluation Gates

- Gate thresholds are declared in `domains/mr_visit_jp/prompts/evaluation_gates.yaml`.
- `GET /v1/evaluation-gates` returns:
  - the current rollout decision for requested vs effective prompt context
  - offline gate results from transcript fixtures plus prompt-contract checks
  - online gate results aggregated from finalized session reviews grouped by prompt profile and experiment id
- Offline fixture coverage is also exposed under `offline_dataset`, including scenario, subskill, compliance-case, and finish-reason gaps.
- Run the local offline report from the repo root with:
  - `make evaluate-mr-visit-jp-fixtures`
  - `make evaluate-mr-visit-jp-fixtures FORMAT=json`
  - `bash scripts/evaluate-mr-visit-jp-fixtures.sh --format json`
- Transcript fixture conventions live in `tests/transcripts/README.md`.
- Hermes proxies the same status at `/v1/evaluation-gates` and `/v1/skills/mr_visit_jp/evaluation-gates`.

## Local Human Review Feedback Loop

- H4 currently ships as a local, append-only data path (not a production reviewer-role workflow).
- Records are versioned and never mutate in place.
- Runtime stores feedback under `${MR_RUNTIME_DATA_DIR}/human_review_feedback/`.
- Local endpoints:
  - `POST /_local/human-review-feedback/records`
  - `GET /_local/human-review-feedback/records`
  - `GET /_local/human-review-feedback/export`
  - `POST /_local/human-review-feedback/import`
  - `GET /_local/human-review-feedback/fixture-candidates`
- Response contracts are validated by shared schemas under `packages/shared-schemas/schemas/runtime_human_review_feedback_*.schema.json`.
- Fixture candidate output is intentionally draft-oriented and aligned to `tests/transcripts` schema fields.
- Candidates can be reviewed and promoted into offline dataset fixtures manually through normal code review.
- Candidate export helpers from repo root:
  - `make export-human-review-fixture-candidates`
  - `bash scripts/export-human-review-fixture-candidates.sh --apply`

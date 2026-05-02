# Session Store And Search Blueprint

This is the reviewed schema target for `R5`.

## Purpose

Define the first production persistence shape before Alembic migrations start,
while keeping the Alpha file-backed adapters valid behind the same runtime
interfaces.

## Current Alpha Inputs

- Session records are serialized by
  `apps/mr-visit-jp-runtime/src/session_engine/state_machine.py` into one JSON
  document per session.
- Event records are appended by
  `apps/mr-visit-jp-runtime/src/persistence/file_event_store.py` as canonical
  envelope JSON lines.
- Progress snapshots are written by
  `apps/mr-visit-jp-runtime/src/services/progress_tracker.py` into one JSON
  document per learner.
- `DomainSessionContext` and the session event envelope remain the canonical
  payload shapes. SQL mode must preserve them losslessly.

## Decisions

- The first SQL migration target is PostgreSQL via Alembic because the repo
  already carries a PostgreSQL dev stack and `alembic.ini` points there.
- Hermes' SQLite WAL and FTS patterns are still useful reference inputs, but
  they do not override the repo's initial database target.
- File-backed adapters remain the default Alpha implementation and must continue
  to satisfy `apps/mr-visit-jp-runtime/src/persistence/interfaces.py`.
- Write repositories stay narrow. Search and supervisor queries should land in a
  separate read-model surface later instead of bloating `SessionStore`,
  `EventStore`, or `ProgressStore`.
- Lossless JSON payloads should be stored, but stable filter fields must also be
  promoted into typed columns so replay and audits do not depend on JSON path
  parsing.
- Full-text search is deferred until SQL mode and query patterns stabilize.
  Phase 1 should use structured indexes only.

## Relational Target

### `learners`

- Primary key: `learner_id`.
- Stable columns: `locale`, `created_at`, `updated_at`, `last_session_at`.
- Purpose: own durable learner identity and give progress snapshots a foreign
  key anchor.

### `prompt_context_snapshots`

- Primary key: `prompt_context_id`.
- Stable columns: `context_hash`, `skill_id`, `prompt_profile`,
  `experiment_id`, `prompt_flags_json`, `contracts_json`, `summary_json`,
  `created_at`.
- Constraints: unique `context_hash`.
- Purpose: store immutable prompt/profile snapshots once and let sessions,
  reviews, and audits refer to the same prompt context without duplicating large
  prompt payloads everywhere.

### `sessions`

- Primary key: `session_id`.
- Foreign keys: `learner_id -> learners`, `prompt_context_id ->
  prompt_context_snapshots`.
- Stable columns: `skill_id`, `capability_id`, `scenario_id`, `persona_id`,
  `locale`, `trace_id`, `prompt_profile`, `experiment_id`, `status`,
  `turn_count`, `finish_reason`, `started_at`, `updated_at`,
  `continuity_context_json`, `context_json`.
- Purpose: own the session lifecycle, replay metadata, and cross-table join
  keys.

### `session_turns`

- Primary key: `turn_id`.
- Foreign key: `session_id -> sessions`.
- Stable columns: `turn_index`, `user_message`, `doctor_reply`,
  `director_phase`, `director_events_json`, `created_at`.
- Constraints: unique `(session_id, turn_index)`.
- Purpose: preserve ordered transcript turns as the replay source of truth.

### `session_events`

- Primary key: `event_id`.
- Foreign keys: `session_id -> sessions`, optional `turn_id -> session_turns`.
- Stable columns: `seq`, `type`, `source`, `stage`, `timestamp`,
  `schema_version`, `skill_id`, `capability_id`, `action_id`, `learner_id`,
  `scenario_id`, `persona_id`, `prompt_profile`, `experiment_id`, `trace_id`,
  `content_json`, `metadata_json`.
- Constraints: unique `(session_id, seq)`.
- Purpose: persist the canonical event envelope with enough typed metadata for
  replay, analytics, audits, and prompt QA.

### `session_reviews`

- Primary key and foreign key: `session_id -> sessions`.
- Foreign key: `prompt_context_id -> prompt_context_snapshots`.
- Stable columns: `overall_score`, `overall_band`, `priority_subskills`,
  `compliance_rule_ids`, `compliance_severities`, `artifact_sources_json`,
  `fallback_reasons_json`, `prompt_profile`, `experiment_id`, `created_at`,
  `payload_json`.
- Purpose: store one finalized review payload per session while exposing the
  fields that supervisor search and compliance audit actually filter on.

### `learner_progress_snapshots`

- Primary key: `progress_snapshot_id`.
- Foreign keys: `learner_id -> learners`, `source_session_id -> sessions`.
- Stable columns: `total_sessions`, `total_exp`, `level`, `updated_at`,
  `subskills_json`, `weakness_clusters_json`, `recent_history_json`,
  `coach_memory_json`, `payload_json`.
- Purpose: preserve the write-time progress projection without forcing the Web
  app to recompute it from sessions on every request.

### `session_recommendations`

- Primary key: `recommendation_id`.
- Foreign keys: `progress_snapshot_id -> learner_progress_snapshots`,
  `learner_id -> learners`, `source_session_id -> sessions`.
- Stable columns: `rank`, `scenario_id`, `title`, `difficulty`,
  `target_subskills`, `reason`, `created_at`.
- Constraints: unique `(progress_snapshot_id, rank)`.
- Purpose: keep the latest recommendation list queryable without parsing the
  whole progress snapshot payload.

## Deliberate Non-Tables In Phase 1

- No standalone diagnosis table yet. Diagnosis details stay inside
  `session_reviews.payload_json` until query shapes justify a normalized child
  table.
- No standalone recent-history table yet. `sessions`, `session_reviews`, and
  `learner_progress_snapshots` already cover replay and trend use cases.
- No search-document table yet. Free-text indexing is explicitly deferred.

## Index Plan

### Replay

- `sessions (learner_id, started_at desc)`
- `sessions (status, updated_at desc)`
- `session_turns unique (session_id, turn_index)`
- `session_events unique (session_id, seq)`
- `session_events (session_id, timestamp)`

### Supervisor Search

- `sessions (scenario_id, started_at desc)`
- `sessions (persona_id, started_at desc)`
- `sessions (prompt_profile, experiment_id, started_at desc)`
- `session_reviews (overall_band, created_at desc)`
- GIN or array-support index on `session_reviews.priority_subskills`
- `session_events (type, stage, timestamp desc)`

### Compliance Audit

- `sessions (trace_id)`
- `session_events (trace_id, timestamp)`
- GIN or array-support index on `session_reviews.compliance_rule_ids`
- GIN or array-support index on `session_reviews.compliance_severities`

### Prompt-Profile QA

- `prompt_context_snapshots unique (context_hash)`
- `prompt_context_snapshots (prompt_profile, experiment_id, created_at desc)`
- `session_reviews (prompt_profile, experiment_id, created_at desc)`
- `session_events (prompt_profile, experiment_id, timestamp desc)`
- `learner_progress_snapshots (learner_id, updated_at desc)`

## Search Phasing

- Phase 1: structured filters only on sessions, reviews, events, and
  recommendations.
- Phase 2: add adapter-owned text search projections after SQL mode is stable
  and we have real query logs.
- Candidate text corpus later: `session_turns.user_message`,
  `session_turns.doctor_reply`, review summaries and strengths from
  `session_reviews.payload_json`, and selected `session_events.content_json`
  fields.
- When text search lands, keep it in a search projection or generated text index
  layer. Do not push search-specific branching into evaluation, scoring, or
  recommendation logic.

## Repository Boundary

- `SessionStore` remains a write/read-by-id surface: `create`, `upsert`, `get`,
  `list_all`.
- `EventStore` remains an append/replay surface: `append`, `replace`,
  `list_events`.
- `ProgressStore` remains a snapshot surface: `upsert`, `get`.
- Future SQL search should arrive as separate query repositories such as
  `SessionQueryStore` or `SessionSearchRepository`, not as extra methods on the
  write adapters.

## Migration Sequence

1. Create the Alembic environment and the eight base tables above.
2. Implement SQL adapters that round-trip the current file payloads through the
   existing persistence interfaces.
3. Add an import path from file-backed data into SQL rows, or a temporary
   dual-write bootstrap.
4. Switch runtime reads from file-backed adapters to SQL adapters behind the
   same interfaces.
5. Only after that, add dedicated supervisor search and optional text search.

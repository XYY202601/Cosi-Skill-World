# event-store

Persistence layer for training events.

## Purpose

Store structured events generated during sessions.

## Current Surface

- Alpha adapter: `apps/mr-visit-jp-runtime/src/persistence/file_event_store.py`
- Runtime contract: `apps/mr-visit-jp-runtime/src/persistence/interfaces.py`

## Canonical Envelope

Each persisted session event uses the runtime envelope:

- `type`
- `source`
- `stage`
- `content`
- `metadata`
- `skill_id`
- `session_id`
- `turn_id`
- `seq`
- `timestamp`
- `schema_version`

Current writer version: `1.1`

## SQL Target

- `session_events`
- typed metadata columns duplicated from the canonical envelope for indexed
  filters
- canonical `content_json` and `metadata_json` retained losslessly

See `docs/architecture/session-store-search-blueprint.md` for the reviewed
schema and index target.

## MR Session Taxonomy

Canonical event categories:

- `opening`
- `profiling`
- `evidence`
- `objection`
- `compliance`
- `closing`
- `recovery`
- `completion`

Current rule-driven director codes:

- `opening`: `opening_overlong`, `opening_missing_permission`, `patient_segment_not_specified`, `time_pressure_not_respected`, `carryover_opening_gap`
- `profiling`: `formulary_barrier_not_explored`, `weak_profiling_signal`, `discovery_question_missing`, `carryover_need_discovery_gap`, `decision_criteria_not_explored`
- `evidence`: `evidence_not_addressed`, `carryover_evidence_gap`, `evidence_detail_missing`, `evidence_dump_without_use_case`, `unsupported_claim_without_evidence`, `patient_use_case_not_defined`
- `objection`: `prior_rejection_not_acknowledged`, `no_new_relevance_after_rejection`, `commitment_too_large_for_cautious_persona`, `unsupported_competitor_comparison`, `unrealistic_adoption_request`
- `compliance`: `safety_first_context`, `safety_reporting_not_started`, `followup_process_not_stated`
- `closing`: `closing_next_step_missing`, `carryover_followup_gap`, `micro_commitment_missing`
- `recovery`: `low_information_turn`, `practical_relevance_not_established`, `need_signal_not_established`
- `completion`: `max_turns_reached`, `session_finalized`

## Turn Event Content

`turn_processed` keeps the legacy replay fields and now also carries structured analytics input:

- `turn_index`
- `director_phase`
- `director_events`
- `recommended_action`
- `status`
- `director`
- `signal_summary`
- `taxonomy`

`signal_summary` is rule-derived and includes:

- boolean coverage flags such as permission, patient segment, evidence, endpoint detail, question, next step, micro-commitment, safety, follow-up process, formulary context, and comparison context
- `token_count`
- `present_signals`
- `missing_core_signals`

`taxonomy` includes:

- `categories`
- `entries`

Each `entries` item carries:

- `code`
- `category`
- `severity`
- `description`

## Why It Matters

Events are critical for:
- diagnosis
- replay
- analytics
- recommendation logic

They also keep the session-level `trace_id` that now appears in runtime review
metadata and HTTP request logs. Request logs must stay body-free; the event
store remains the structured place to inspect session details.

## Search Boundary

Phase 1 search is structured only.
Full-text indexing of event content is deferred until SQL mode stabilizes.

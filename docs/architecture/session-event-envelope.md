# Session Event Envelope

This is the implemented contract for `R3`.

## Purpose

Standardize persisted events, future live streaming, replay, and analytics around
one schema shape instead of ad-hoc event payloads.

## Current Implementation

- Runtime module: `apps/mr-visit-jp-runtime/src/session_events.py`
- Persistence surface: `apps/mr-visit-jp-runtime/src/persistence/file_event_store.py`
- Schema file: `packages/shared-schemas/schemas/session_event_envelope.schema.json`
- Current writer version: `1.1`
- Current emitters:
  - `SessionEngine` live session flow
  - demo seed event generation

Older file events are normalized on read into the canonical envelope and re-sequenced
by timestamp when `seq` is missing.

`turn_processed` now carries rule-derived `signal_summary` and `taxonomy` content so
replay, recommendation, and analytics do not need to reverse-engineer free-form event names.

## Proposed Envelope

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

## Boundary Rule

The envelope should stay transport-agnostic.
It can be written to files now and reused for WebSocket streaming later.

## Current Tests

- `tests/integration/test_session_event_envelope_contract.py`
- `apps/mr-visit-jp-runtime/tests/test_runtime_api.py`
- `apps/mr-visit-jp-runtime/tests/test_demo_progress_seed.py`

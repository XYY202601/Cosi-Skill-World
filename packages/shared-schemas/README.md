# shared-schemas

Schema definitions for structured AI and service outputs.

## Purpose

Provide strict validation targets for:
- Judge output
- Coach output
- compliance flags
- scenario YAML
- skill manifests

## Why It Exists

LLM-generated outputs must be normalized and validated.
This package reduces drift and improves runtime safety.

## Current Expected Schemas

- `judge_review.schema.json`
- `coach_feedback.schema.json`
- `compliance_flags.schema.json`
- `mr_scenario.schema.json`
- `skill_manifest.schema.json`
- `runtime_health_response.schema.json`
- `session_event_envelope.schema.json`
- `runtime_scenario_list_response.schema.json`
- `runtime_session_start_response.schema.json`
- `runtime_session_response.schema.json`
- `runtime_send_turn_response.schema.json`
- `runtime_finish_session_response.schema.json`
- `runtime_review_response.schema.json`
- `runtime_progress_snapshot_response.schema.json`
- `runtime_session_events_response.schema.json`
- `runtime_evaluation_gates_response.schema.json`
- `runtime_organization_reports_response.schema.json`

## Related Runtime Contracts

- Domain session context: `docs/architecture/domain-session-context.md`
- Session event envelope target: `docs/architecture/session-event-envelope.md`
- Runtime API contract: `docs/api/mr-visit-jp-runtime-api.md`

## Runtime Contract Vocabulary

Required runtime actions:

- `healthz` via `runtime.health_path`
- `list_scenarios`
- `start_session`
- `get_session`
- `send_turn`
- `finish_session`
- `get_review`
- `get_session_events`
- `get_progress_snapshot`

Optional standardized actions:

- `get_evaluation_gates`
- `get_curriculum`
- `get_organization_reports`

## Ownership Rule

Use shared schemas for wire-visible payloads that cross service boundaries or
need regression protection across runtime, Hermes, and Web.

- Runtime owns executable response models in `apps/mr-visit-jp-runtime/src/main.py`
- Shared schemas own regression-testable JSON response shapes
- Web owns its TypeScript mirror in `apps/web/src/lib/runtime-api.ts` until
  `packages/shared-types` is promoted into a buildable workspace package

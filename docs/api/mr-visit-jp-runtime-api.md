# MR Visit JP Runtime API (Alpha)

This document is the executable reference for the minimum domain runtime
contract. A future runtime should be able to follow this spec without reading
MR-specific implementation internals.

## Base Rules

- Runtime health is exposed at `GET /healthz`.
- Versioned domain actions live under `runtime.base_path`, currently `/v1`.
- Hermes proxies runtime payloads as-is. Runtime owns response models and schema stability.
- Required action ids and optional action ids are declared in `skill_manifest.schema.json`.

## Required Runtime Contract

| Contract item | Action id | Method | Path | Shared schema |
| --- | --- | --- | --- | --- |
| health | `healthz` | `GET` | `/healthz` | `runtime_health_response.schema.json` |
| scenarios | `list_scenarios` | `GET` | `/v1/scenarios` | `runtime_scenario_list_response.schema.json` |
| start session | `start_session` | `POST` | `/v1/sessions/start` | `runtime_session_start_response.schema.json` |
| get session | `get_session` | `GET` | `/v1/sessions/{session_id}` | `runtime_session_response.schema.json` |
| send turn | `send_turn` | `POST` | `/v1/sessions/{session_id}/turn` | `runtime_send_turn_response.schema.json` |
| finish session | `finish_session` | `POST` | `/v1/sessions/{session_id}/finish` | `runtime_finish_session_response.schema.json` |
| review | `get_review` | `GET` | `/v1/sessions/{session_id}/review` | `runtime_review_response.schema.json` |
| events | `get_session_events` | `GET` | `/v1/sessions/{session_id}/events` | `runtime_session_events_response.schema.json` |
| progress | `get_progress_snapshot` | `GET` | `/v1/learners/{learner_id}/progress` | `runtime_progress_snapshot_response.schema.json` |

## Optional Standardized Actions

| Contract item | Action id | Method | Path | Notes |
| --- | --- | --- | --- | --- |
| evaluation gates | `get_evaluation_gates` | `GET` | `/v1/evaluation-gates` | Shared schema exists today: `runtime_evaluation_gates_response.schema.json` |
| curriculum | `get_curriculum` | `GET` | `/v1/curriculum` | Canonical action id/path reserved for future curriculum APIs |
| organization reports | `get_organization_reports` | `GET` | `/v1/organizations/{organization_id}/reports` | Shared schema exists today: `runtime_organization_reports_response.schema.json` |

Current MR runtime implements `get_evaluation_gates` and
`get_organization_reports`. The other optional actions should be omitted from a
skill manifest until the runtime actually supports them.

## Response Contract Ownership

Runtime response ownership is split across three layers:

- executable response models: `apps/mr-visit-jp-runtime/src/main.py`
- regression schemas: `packages/shared-schemas/schemas/runtime_*.schema.json`
- current Web TypeScript mirror: `apps/web/src/lib/runtime-api.ts`

Compatibility rules:

- Additive fields must keep existing required fields stable.
- Breaking shape changes require schema and Web type updates in the same change.
- `GET /v1/sessions/{id}/events` returns canonical event envelopes; event-specific fields live under `event.content`.

`GET /v1/learners/{learner_id}/progress` now includes a `curriculum` object
that explains the learner's current stage, why promotion has or has not
happened, stage metrics, and the current-stage scenario checklist used during
recommendation ranking.

## Review Payload Notes

`GET /v1/sessions/{id}/review` and finish responses return `review.subskills[*].evidence`.

- Older records may still store plain evidence strings.
- Newer records may include structured evidence objects with:
  - `summary`
  - `turn_index`
  - `speaker`
  - `excerpt`
  - `tags`

## Event Payload

`GET /v1/sessions/{session_id}/events` returns:

- `session_id`
- `event_count`
- `events`

Each item in `events` uses the canonical session event envelope:

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

Current runtime writer version: `1.1`

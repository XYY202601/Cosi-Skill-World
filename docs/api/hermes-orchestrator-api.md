# Hermes Orchestrator API (Alpha)

Hermes owns the public route surface. It should stay thin: resolve skill,
resolve action, build runtime path, proxy the request, preserve payload/status
and tracing headers.

## Current Endpoints

- `GET /healthz`
- `GET /v1/skills`
- `GET /v1/scenarios`
- `GET /v1/evaluation-gates`
- `POST /v1/sessions/start`
- `GET /v1/sessions/{id}`
- `POST /v1/sessions/{id}/turn`
- `POST /v1/sessions/{id}/finish`
- `GET /v1/sessions/{id}/review`
- `GET /v1/sessions/{id}/events`
- `GET /v1/learners/{id}/progress`
- `GET /v1/organizations/{organization_id}/reports`
- `GET /v1/skills/{skill_id}/...` skill-scoped variants for the same actions

## Runtime Contract Surface

Every registered domain runtime must expose:

| Contract item | Action id | Hermes root route | Hermes skill route | Runtime route |
| --- | --- | --- | --- | --- |
| health | `healthz` | n/a | n/a | `GET runtime.health_path` |
| scenarios | `list_scenarios` | `GET /v1/scenarios` | `GET /v1/skills/{skill_id}/scenarios` | `GET /v1/scenarios` |
| start session | `start_session` | `POST /v1/sessions/start` | `POST /v1/skills/{skill_id}/sessions/start` | `POST /v1/sessions/start` |
| get session | `get_session` | `GET /v1/sessions/{session_id}` | `GET /v1/skills/{skill_id}/sessions/{session_id}` | `GET /v1/sessions/{session_id}` |
| send turn | `send_turn` | `POST /v1/sessions/{session_id}/turn` | `POST /v1/skills/{skill_id}/sessions/{session_id}/turn` | `POST /v1/sessions/{session_id}/turn` |
| finish session | `finish_session` | `POST /v1/sessions/{session_id}/finish` | `POST /v1/skills/{skill_id}/sessions/{session_id}/finish` | `POST /v1/sessions/{session_id}/finish` |
| review | `get_review` | `GET /v1/sessions/{session_id}/review` | `GET /v1/skills/{skill_id}/sessions/{session_id}/review` | `GET /v1/sessions/{session_id}/review` |
| events | `get_session_events` | `GET /v1/sessions/{session_id}/events` | `GET /v1/skills/{skill_id}/sessions/{session_id}/events` | `GET /v1/sessions/{session_id}/events` |
| progress | `get_progress_snapshot` | `GET /v1/learners/{learner_id}/progress` | `GET /v1/skills/{skill_id}/learners/{learner_id}/progress` | `GET /v1/learners/{learner_id}/progress` |

Optional standardized action ids:

- `get_evaluation_gates`
- `get_curriculum`
- `get_organization_reports`

Current Hermes route coverage includes `get_evaluation_gates`. The other
optional action ids are reserved in the shared manifest vocabulary so future
runtimes can declare them without inventing new names. Current Hermes route
coverage also includes `get_organization_reports`.

## Registry Rule

Hermes owns the public route surface, but skill/action/runtime resolution must
come from `packages/skill-registry`.

`GET /v1/skills` returns:

- `skills`: ordered list of registered skill ids
- `default_skill_id`: the default skill for unscoped routes
- `items`: per-skill metadata including runtime, capabilities, actions, and UI summary

Domain spikes may keep a manifest in-repo with `registration.enabled: false`.
Those manifests are not exposed by default Hermes registry discovery.

## Proxy Contract Rule

For proxied runtime responses, Hermes must preserve:

- HTTP status code
- JSON payload body
- tracing headers needed for request/session correlation

Schema validation remains owned by runtime/shared schemas. Hermes should not
translate runtime payloads.

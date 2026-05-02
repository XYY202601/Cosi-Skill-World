# Skill Registry Contract

This document defines the vocabulary that Hermes and future domain runtimes must
share when using `packages/skill-registry`.

## Vocabulary

- `skill`: a domain package identified by `skill_id`
- `capability`: a grouped slice of behavior inside one skill
- `action`: a concrete runtime operation that Hermes can route
- `runtime path`: the path template under the runtime's `base_path`
- `surface`: where Hermes exposes the action
  - `root`: unscoped route such as `/v1/scenarios`
  - `skill`: skill-scoped route such as `/v1/skills/{skill_id}/scenarios`

## Runtime Contract Action Set

Required:

- `healthz` via `runtime.health_path`
- `list_scenarios`
- `start_session`
- `get_session`
- `send_turn`
- `finish_session`
- `get_review`
- `get_session_events`
- `get_progress_snapshot`

Optional standardized ids:

- `get_evaluation_gates`
- `get_curriculum`
- `get_organization_reports`

## Current Capability Set

- `scenario_catalog`
- `practice_session`
- `review`
- `progress`

## Hermes Migration Rule

Hermes should keep explicit FastAPI routes for now, but route resolution must come
from the registry:

1. resolve skill id
2. resolve action id
3. build runtime path from action path template + path params
4. read runtime base URL from the manifest's `base_url_env`
5. proxy to the runtime

This keeps backward-compatible URLs while removing hard-coded skill and action
knowledge from Hermes.

## R2 Hook: Domain Session Context

The next shared contract should introduce a `DomainSessionContext` carrying:

- `skill_id`
- `capability_id`
- `action_id`
- `session_id`
- `turn_id`
- `learner_id`
- `scenario_id`
- `prompt_profile`
- `experiment_id`
- `trace_id`

## R3 Hook: Event Envelope

The next shared contract should standardize one event envelope carrying:

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

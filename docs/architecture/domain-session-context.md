# Domain Session Context

This is the implemented contract for `R2`.

## Purpose

Reduce parameter drift across runtime session handling, review generation,
continuity, events, and future analytics.

## Current Implementation

- Runtime module: `apps/mr-visit-jp-runtime/src/runtime_context.py`
- Primary owner: `SessionEngine`
- Persistence surface: session JSON payloads now store `context`
- Propagation surfaces:
  - persisted events under `event.metadata`
  - review artifacts under `review.meta.context`

## Proposed Core Fields

- `skill_id`
- `capability_id`
- `action_id`
- `session_id`
- `turn_id`
- `learner_id`
- `scenario_id`
- `persona_id`
- `prompt_profile`
- `experiment_id`
- `prompt_flags`
- `locale`
- `trace_id`
- `continuity_context`

## Boundary Rule

This context belongs to domain runtimes and shared packages.
It must not contain Web-only UI state or Hermes-only proxy internals.

## Current Tests

- `tests/integration/test_domain_session_context_contract.py`
- `apps/mr-visit-jp-runtime/tests/test_runtime_api.py`

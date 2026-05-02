# hermes-orchestrator

Thin platform-level orchestrator for `cosi-skill-world`.

## Purpose

This service is our own product implementation of the "Hermes layer":
- intent understanding
- skill package selection
- training session entry routing
- progress summary
- post-session archival
- cross-skill recommendation

## Important Boundary

This service does **not** run turn-by-turn domain dialogue.

It must remain thin.

## Responsibilities

- map user requests to domain skills
- start domain sessions
- resume domain sessions
- fetch reviews
- fetch learner progress snapshots
- store high-level memory summaries
- recommend next training direction

## Non-Responsibilities

- doctor roleplay
- scenario control
- scoring
- diagnosis generation
- compliance judgment
- turn-level runtime management

Those belong to domain runtimes such as `mr-visit-jp-runtime` and `gp-visit-jp-runtime`.

## Registered Skill Packages

- `mr_visit_jp` as the default unscoped skill
- `gp_visit_jp` as the second-domain spike exposed through skill-scoped routes

## Expected Actions

- `list_scenarios`
- `start_session`
- `get_session`
- `send_turn`
- `finish_session`
- `get_review`
- `get_session_events`
- `get_progress_snapshot`
- `get_evaluation_gates` where the runtime exposes it

## Runtime Boundary

- Hermes forwards the shared runtime contract to per-domain runtimes.
- Default MR runtime base: `http://127.0.0.1:8100`
- Default GP runtime base: `http://127.0.0.1:8200`
- Override with `MR_VISIT_JP_RUNTIME_BASE` and `GP_VISIT_JP_RUNTIME_BASE`

## Design Principle

Hermes is the platform brain, not the domain actor.

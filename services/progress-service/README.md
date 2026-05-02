# progress-service

Learner progression update service.

## Purpose

Update learner skill levels after each completed session.

## Current Surface

- Alpha adapter: `apps/mr-visit-jp-runtime/src/persistence/file_progress_store.py`
- Runtime owner: `apps/mr-visit-jp-runtime/src/services/progress_tracker.py`
- Runtime contract: `apps/mr-visit-jp-runtime/src/persistence/interfaces.py`

## Responsibilities

- apply EXP gains
- update subskill levels
- store progression history
- compute trend snapshots
- persist recommendation projections

## Inputs

- weighted review result
- target subskills
- scenario difficulty
- recommendation signals

## Output

- updated learner progress
- delta summary
- next focus suggestions

## SQL Target

- `learner_progress_snapshots`
- `session_recommendations`

`recent_history` stays inside the snapshot payload in Phase 1 because session
and review tables already provide the source-of-truth history surface.

See `docs/architecture/session-store-search-blueprint.md` for the reviewed
schema target.

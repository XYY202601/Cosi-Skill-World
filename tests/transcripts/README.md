# Transcript Fixtures

This directory is the offline evaluation dataset for `mr_visit_jp`.

## Layout

- Store each fixture under `tests/transcripts/<bucket>/`.
- Allowed buckets are `good`, `medium`, `bad`, `compliance`, and `continuity`.
- Keep `name` identical to the JSON file stem.

## Required Fixture Fields

Each fixture must define:

- `name`
- `finish_reason`
- `scenario_focus_subskills`
- `turns`
- `expected`
- `metadata`

`metadata` must include:

- `schema_version`: currently `1`
- `scenario_ids`: one or more scenario ids from `domains/mr_visit_jp/scenarios/`
- `compliance_case`: one of `none`, `overclaim_and_competitor`, `adverse_event_correct`, `adverse_event_failure`
- `tags`: one or more short dataset labels

## Finish Reasons

Supported `finish_reason` values:

- `manual_finish`
- `learner_requested_finish`
- `max_turns_reached`
- `director_signaled_completion`

## Validation And Reporting

- `./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_transcript_fixture_evaluation.py`
- `make evaluate-mr-visit-jp-fixtures`

The offline report summarizes coverage for scenarios, subskills, compliance cases, and finish reasons.

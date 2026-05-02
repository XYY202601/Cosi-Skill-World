from __future__ import annotations

import json
import difflib
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from scenarios.asset_loader import DomainBundle


REPO_ROOT = Path(__file__).resolve().parents[4]
TRANSCRIPTS_DIR = REPO_ROOT / "tests" / "transcripts"
FIXTURE_SCHEMA_VERSION = 1
ALLOWED_FIXTURE_BUCKETS = ("good", "medium", "bad", "compliance", "continuity")
KNOWN_COMPLIANCE_CASES = (
    "none",
    "overclaim_and_competitor",
    "adverse_event_correct",
    "adverse_event_failure",
)
KNOWN_FINISH_REASONS = (
    "manual_finish",
    "learner_requested_finish",
    "max_turns_reached",
    "director_signaled_completion",
)
FIXTURE_BASE_TIMESTAMP = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _non_empty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label)
    return value.strip()


def _string_list(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(label)
    output: list[str] = []
    for item in value:
        output.append(_non_empty_string(item, label=label))
    return output


def _optional_string_list(value: Any, *, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(label)
    output: list[str] = []
    for item in value:
        output.append(_non_empty_string(item, label=label))
    return output


def _integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label)
    return int(value)


def _optional_score_map(value: Any, *, label: str) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(label)
    output: dict[str, int] = {}
    for subskill_id, score in value.items():
        normalized_subskill_id = _non_empty_string(
            subskill_id,
            label=f"{label} key must be non-empty string",
        )
        output[normalized_subskill_id] = _integer(
            score,
            label=f"{label}.{normalized_subskill_id} must be numeric",
        )
    return output


def _normalize_expected(expected: Any, *, fixture_label: str) -> dict[str, Any]:
    if not isinstance(expected, dict):
        raise ValueError(f"fixture `{fixture_label}` must define object `expected`")

    overall_score_min = _integer(
        expected.get("overall_score_min"),
        label=f"fixture `{fixture_label}` expected.overall_score_min must be numeric",
    )
    overall_score_max = _integer(
        expected.get("overall_score_max"),
        label=f"fixture `{fixture_label}` expected.overall_score_max must be numeric",
    )
    if overall_score_min < 0 or overall_score_max > 100 or overall_score_min > overall_score_max:
        raise ValueError(
            f"fixture `{fixture_label}` expected overall score range must be within 0-100 and min<=max"
        )

    overall_band_one_of = _string_list(
        expected.get("overall_band_one_of"),
        label=f"fixture `{fixture_label}` expected.overall_band_one_of must be non-empty list",
    )

    normalized = dict(expected)
    normalized["overall_score_min"] = overall_score_min
    normalized["overall_score_max"] = overall_score_max
    normalized["overall_band_one_of"] = overall_band_one_of
    normalized["required_diagnosis_ids"] = _optional_string_list(
        expected.get("required_diagnosis_ids"),
        label=f"fixture `{fixture_label}` expected.required_diagnosis_ids must be list",
    )
    normalized["forbidden_diagnosis_ids"] = _optional_string_list(
        expected.get("forbidden_diagnosis_ids"),
        label=f"fixture `{fixture_label}` expected.forbidden_diagnosis_ids must be list",
    )
    normalized["required_compliance_rule_ids"] = _optional_string_list(
        expected.get("required_compliance_rule_ids"),
        label=f"fixture `{fixture_label}` expected.required_compliance_rule_ids must be list",
    )
    normalized["forbidden_compliance_rule_ids"] = _optional_string_list(
        expected.get("forbidden_compliance_rule_ids"),
        label=f"fixture `{fixture_label}` expected.forbidden_compliance_rule_ids must be list",
    )
    normalized["required_compliance_severities"] = _optional_string_list(
        expected.get("required_compliance_severities"),
        label=f"fixture `{fixture_label}` expected.required_compliance_severities must be list",
    )
    normalized["forbidden_compliance_severities"] = _optional_string_list(
        expected.get("forbidden_compliance_severities"),
        label=f"fixture `{fixture_label}` expected.forbidden_compliance_severities must be list",
    )
    normalized["required_subskill_score_min"] = _optional_score_map(
        expected.get("required_subskill_score_min"),
        label=f"fixture `{fixture_label}` expected.required_subskill_score_min",
    )
    normalized["required_subskill_score_max"] = _optional_score_map(
        expected.get("required_subskill_score_max"),
        label=f"fixture `{fixture_label}` expected.required_subskill_score_max",
    )
    return normalized


def list_transcript_fixture_paths(root: Path = TRANSCRIPTS_DIR) -> list[Path]:
    return sorted(root.rglob("*.json"))


def _fixture_relative_parts(path: Path, *, root: Path) -> tuple[str, ...]:
    relative = path.relative_to(root)
    if len(relative.parts) < 2:
        raise ValueError(
            f"fixture `{relative.as_posix()}` must live under tests/transcripts/<bucket>/"
        )
    return relative.parts


def fixture_bucket(path: Path, *, root: Path = TRANSCRIPTS_DIR) -> str:
    bucket = _fixture_relative_parts(path, root=root)[0]
    if bucket not in ALLOWED_FIXTURE_BUCKETS:
        raise ValueError(
            f"fixture `{path.relative_to(root).as_posix()}` uses unsupported bucket `{bucket}`"
        )
    return bucket


def load_transcript_fixture(path: Path, *, root: Path = TRANSCRIPTS_DIR) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"fixture must be object: {path}")

    relative = path.relative_to(root)
    bucket = fixture_bucket(path, root=root)
    name = _non_empty_string(
        payload.get("name"),
        label=f"fixture `{relative.as_posix()}` missing non-empty `name`",
    )
    if name != path.stem:
        raise ValueError(
            f"fixture `{relative.as_posix()}` name `{name}` must match file stem `{path.stem}`"
        )

    finish_reason = _non_empty_string(
        payload.get("finish_reason"),
        label=f"fixture `{relative.as_posix()}` missing non-empty `finish_reason`",
    )
    if finish_reason not in KNOWN_FINISH_REASONS:
        raise ValueError(
            f"fixture `{relative.as_posix()}` uses unsupported finish_reason `{finish_reason}`"
        )

    scenario_focus_subskills = _string_list(
        payload.get("scenario_focus_subskills"),
        label=f"fixture `{relative.as_posix()}` missing non-empty `scenario_focus_subskills`",
    )

    turns = payload.get("turns")
    if not isinstance(turns, list) or not turns:
        raise ValueError(f"fixture `{relative.as_posix()}` must define non-empty `turns`")

    expected = _normalize_expected(
        payload.get("expected"),
        fixture_label=relative.as_posix(),
    )

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError(f"fixture `{relative.as_posix()}` must define object `metadata`")

    schema_version = metadata.get("schema_version")
    if schema_version != FIXTURE_SCHEMA_VERSION:
        raise ValueError(
            f"fixture `{relative.as_posix()}` must use metadata.schema_version="
            f"{FIXTURE_SCHEMA_VERSION}"
        )

    scenario_ids = _string_list(
        metadata.get("scenario_ids"),
        label=f"fixture `{relative.as_posix()}` metadata.scenario_ids must be non-empty",
    )
    compliance_case = _non_empty_string(
        metadata.get("compliance_case"),
        label=f"fixture `{relative.as_posix()}` metadata.compliance_case must be non-empty",
    )
    if compliance_case not in KNOWN_COMPLIANCE_CASES:
        raise ValueError(
            f"fixture `{relative.as_posix()}` uses unsupported compliance_case "
            f"`{compliance_case}`"
        )
    tags = _string_list(
        metadata.get("tags"),
        label=f"fixture `{relative.as_posix()}` metadata.tags must be non-empty",
    )

    normalized = dict(payload)
    normalized["finish_reason"] = finish_reason
    normalized["scenario_focus_subskills"] = scenario_focus_subskills
    normalized["expected"] = expected
    normalized["metadata"] = {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "scenario_ids": scenario_ids,
        "compliance_case": compliance_case,
        "tags": tags,
        "bucket": bucket,
        "relative_path": relative.as_posix(),
    }
    return normalized


def transcript_fixture_to_turns(fixture_turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for index, item in enumerate(fixture_turns, start=1):
        created_at = (FIXTURE_BASE_TIMESTAMP + timedelta(seconds=index)).isoformat().replace(
            "+00:00",
            "Z",
        )
        turns.append(
            {
                "turn_index": index,
                "user_message": str(item.get("user_message", "")),
                "doctor_reply": "",
                "director_phase": "exploration",
                "director_events": list(item.get("director_events", [])),
                "created_at": created_at,
            }
        )
    return turns


def summarize_transcript_fixture(
    path: Path,
    fixture: dict[str, Any],
    *,
    root: Path = TRANSCRIPTS_DIR,
) -> dict[str, Any]:
    metadata = fixture["metadata"]
    return {
        "fixture_name": str(fixture["name"]),
        "fixture_path": path.relative_to(root).as_posix(),
        "bucket": str(metadata["bucket"]),
        "scenario_ids": list(metadata["scenario_ids"]),
        "focus_subskills": list(fixture["scenario_focus_subskills"]),
        "finish_reason": str(fixture["finish_reason"]),
        "compliance_case": str(metadata["compliance_case"]),
        "tags": list(metadata["tags"]),
    }


def summarize_transcript_fixture_dataset(
    domain_bundle: DomainBundle,
    *,
    root: Path = TRANSCRIPTS_DIR,
) -> dict[str, Any]:
    fixture_paths = list_transcript_fixture_paths(root)
    fixtures = [load_transcript_fixture(path, root=root) for path in fixture_paths]
    fixture_summaries = [
        summarize_transcript_fixture(path, fixture, root=root)
        for path, fixture in zip(fixture_paths, fixtures, strict=True)
    ]

    known_scenarios = set(domain_bundle.scenarios.keys())
    scenario_counts: Counter[str] = Counter()
    subskill_counts: Counter[str] = Counter()
    compliance_case_counts: Counter[str] = Counter()
    finish_reason_counts: Counter[str] = Counter()
    bucket_counts: Counter[str] = Counter()

    for fixture_summary in fixture_summaries:
        bucket_counts.update([str(fixture_summary["bucket"])])
        finish_reason_counts.update([str(fixture_summary["finish_reason"])])
        compliance_case_counts.update([str(fixture_summary["compliance_case"])])
        scenario_ids = list(fixture_summary["scenario_ids"])
        unknown_scenarios = sorted(set(scenario_ids) - known_scenarios)
        if unknown_scenarios:
            raise ValueError(
                f"fixture `{fixture_summary['fixture_path']}` references unknown scenarios: "
                f"{unknown_scenarios}"
            )
        scenario_counts.update(scenario_ids)
        subskill_counts.update(list(fixture_summary["focus_subskills"]))

    known_subskills = set(domain_bundle.skill_model["subskills"].keys())
    unknown_subskills = sorted(set(subskill_counts.keys()) - known_subskills)
    if unknown_subskills:
        raise ValueError(f"fixtures reference unknown subskills: {unknown_subskills}")

    return {
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "fixture_count": len(fixture_summaries),
        "fixtures_by_bucket": {
            bucket: int(bucket_counts.get(bucket, 0))
            for bucket in ALLOWED_FIXTURE_BUCKETS
            if bucket_counts.get(bucket, 0) > 0
        },
        "coverage": {
            "scenarios": {
                "covered": sorted(scenario_counts.keys()),
                "missing": sorted(known_scenarios - set(scenario_counts.keys())),
                "counts": dict(sorted(scenario_counts.items())),
            },
            "subskills": {
                "covered": sorted(subskill_counts.keys()),
                "missing": sorted(known_subskills - set(subskill_counts.keys())),
                "counts": dict(sorted(subskill_counts.items())),
            },
            "compliance_cases": {
                "covered": sorted(compliance_case_counts.keys()),
                "missing": sorted(set(KNOWN_COMPLIANCE_CASES) - set(compliance_case_counts.keys())),
                "counts": dict(sorted(compliance_case_counts.items())),
            },
            "finish_reasons": {
                "covered": sorted(finish_reason_counts.keys()),
                "missing": sorted(set(KNOWN_FINISH_REASONS) - set(finish_reason_counts.keys())),
                "counts": dict(sorted(finish_reason_counts.items())),
            },
        },
        "fixtures": fixture_summaries,
    }


def lint_transcript_fixture(fixture: dict[str, Any]) -> list[str]:
    """
    Returns a list of quality warnings/errors for a transcript fixture.
    Checks for:
    - Low-information turns (e.g. less than 15 characters, unless tagged 'low_information')
    - Duplicate message patterns (unless tagged 'repeat_message')
    """
    issues = []
    turns = fixture.get("turns", [])
    tags = fixture.get("metadata", {}).get("tags", [])
    
    seen_messages: list[str] = []
    
    for i, turn in enumerate(turns):
        msg = turn.get("user_message", "").strip()
        if not msg:
            continue
            
        # Check low information
        if "low_information" not in tags:
            # We define low information as very short string
            if len(msg) < 15:
                issues.append(f"Turn {i}: Low-information message ('{msg}')")
                
        # Check duplicate
        if "repeat_message" not in tags:
            msg_lower = msg.lower()
            for prev in seen_messages:
                similarity = difflib.SequenceMatcher(None, msg_lower, prev).ratio()
                if similarity > 0.8:
                    issues.append(f"Turn {i}: Duplicate message pattern (similarity={similarity:.2f}, '{msg}')")
                    break
            seen_messages.append(msg_lower)
            
    return issues


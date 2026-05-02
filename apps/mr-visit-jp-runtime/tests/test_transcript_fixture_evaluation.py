from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.review_builder import build_runtime_review
from scenarios.asset_loader import get_domain_bundle
from services.evaluation_fixture_dataset import (
    list_transcript_fixture_paths,
    load_transcript_fixture,
    summarize_transcript_fixture_dataset,
    transcript_fixture_to_turns,
    lint_transcript_fixture,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
TRANSCRIPTS_DIR = REPO_ROOT / "tests" / "transcripts"
FIXTURE_CASES = list_transcript_fixture_paths()


@pytest.mark.parametrize(
    "fixture_path",
    FIXTURE_CASES,
    ids=lambda path: path.relative_to(TRANSCRIPTS_DIR).as_posix(),
)
def test_transcript_fixtures_drive_stable_evaluation_contract(
    fixture_path: Path,
) -> None:
    fixture = load_transcript_fixture(fixture_path)
    expected = fixture["expected"]
    assert fixture["name"] == fixture_path.stem
    turns = transcript_fixture_to_turns(fixture["turns"])

    bundle = get_domain_bundle()
    subskill_weights = {
        subskill_id: float(payload["weight"])
        for subskill_id, payload in bundle.skill_model["subskills"].items()
    }

    review = build_runtime_review(
        turns=turns,
        turn_count=len(turns),
        finish_reason=str(fixture.get("finish_reason", "manual_finish")),
        scenario_focus_subskills=list(fixture["scenario_focus_subskills"]),
        subskill_weights=subskill_weights,
        skill_model=bundle.skill_model,
        diagnosis_types=bundle.diagnosis_types,
        compliance_rules=bundle.compliance_rules,
        score_schema=bundle.score_schema,
        judge_review_schema=bundle.judge_review_schema,
        coach_feedback_schema=bundle.coach_feedback_schema,
        compliance_flags_schema=bundle.compliance_flags_schema,
        model_artifacts=None,
        model_error=None,
        continuity_context=fixture.get("continuity_context"),
    )

    assert review["meta"]["artifact_sources"] == {
        "judge": "rule",
        "coach": "rule",
        "compliance": "rule",
    }

    overall_score = int(review["overall_score"])
    assert overall_score >= int(expected["overall_score_min"])
    assert overall_score <= int(expected["overall_score_max"])
    assert review["overall_band"] in list(expected["overall_band_one_of"])

    diagnosis_ids = {item["id"] for item in review["diagnosis"]["primary"]}
    for required_diagnosis_id in expected.get("required_diagnosis_ids", []):
        assert required_diagnosis_id in diagnosis_ids
    for forbidden_diagnosis_id in expected.get("forbidden_diagnosis_ids", []):
        assert forbidden_diagnosis_id not in diagnosis_ids

    compliance_flags = review["compliance_flags"]
    compliance_rule_ids = {item["rule_id"] for item in compliance_flags}
    for required_rule_id in expected.get("required_compliance_rule_ids", []):
        assert required_rule_id in compliance_rule_ids
    for forbidden_rule_id in expected.get("forbidden_compliance_rule_ids", []):
        assert forbidden_rule_id not in compliance_rule_ids

    severities = {str(item.get("severity", "")) for item in compliance_flags}
    for required_severity in expected.get("required_compliance_severities", []):
        assert required_severity in severities
    for forbidden_severity in expected.get("forbidden_compliance_severities", []):
        assert forbidden_severity not in severities

    required_subskill_score_min = expected.get("required_subskill_score_min", {})
    if isinstance(required_subskill_score_min, dict):
        for subskill_id, min_score in required_subskill_score_min.items():
            assert int(review["subskills"][subskill_id]["score"]) >= int(min_score)

    required_subskill_score_max = expected.get("required_subskill_score_max", {})
    if isinstance(required_subskill_score_max, dict):
        for subskill_id, max_score in required_subskill_score_max.items():
            assert int(review["subskills"][subskill_id]["score"]) <= int(max_score)

    for subskill_id in review["priority_subskills"]:
        evidence_items = review["subskills"][subskill_id]["evidence"]
        assert any(
            isinstance(item, dict) and isinstance(item.get("turn_index"), int) and item["turn_index"] > 0
            for item in evidence_items
        )

    _assert_training_quality(fixture, review)


def _assert_training_quality(fixture: dict, review: dict) -> None:
    tq = fixture.get("expected", {}).get("training_quality")
    if not isinstance(tq, dict):
        return

    if "evidence_per_subskill_min" in tq:
        min_evidence = int(tq["evidence_per_subskill_min"])
        for subskill_id, payload in review["subskills"].items():
            evidence = payload.get("evidence", [])
            assert len(evidence) >= min_evidence, (
                f"Subskill {subskill_id} has {len(evidence)} evidence items, "
                f"expected at least {min_evidence}"
            )

    if tq.get("require_turn_references"):
        for subskill_id, payload in review["subskills"].items():
            evidence = payload.get("evidence", [])
            assert any(
                isinstance(item, dict) and isinstance(item.get("turn_index"), int) and item["turn_index"] > 0
                for item in evidence
            ), f"Subskill {subskill_id} missing turn-indexed evidence"

    if "diagnosis_count_min" in tq:
        assert len(review["diagnosis"]["primary"]) >= int(tq["diagnosis_count_min"])

    if "diagnosis_count_max" in tq:
        assert len(review["diagnosis"]["primary"]) <= int(tq["diagnosis_count_max"])

    if "coaching_action_count_min" in tq:
        min_actions = int(tq["coaching_action_count_min"])
        actions = review.get("coaching_feedback", {}).get("next_actions", [])
        assert len(actions) >= min_actions, (
            f"Expected at least {min_actions} coaching actions, got {len(actions)}"
        )

    if tq.get("continuity_channel_present"):
        assert "continuity_channel" in review, "continuity_channel missing from review"

    compliance_detection = tq.get("compliance_detection")
    if compliance_detection == "none":
        severities = {str(f.get("severity", "")) for f in review.get("compliance_flags", [])}
        assert not (severities & {"high", "critical"}), (
            f"Expected no compliance risk but found severities: {severities}"
        )
    elif compliance_detection == "critical":
        severities = {str(f.get("severity", "")) for f in review.get("compliance_flags", [])}
        assert "critical" in severities, "Expected critical compliance flag but none found"
    elif compliance_detection == "risk":
        severities = {str(f.get("severity", "")) for f in review.get("compliance_flags", [])}
        assert severities & {"high", "critical"}, (
            f"Expected high/critical compliance flag but found: {severities}"
        )
    elif compliance_detection == "positive_only":
        flags = review.get("compliance_flags", [])
        assert any(str(f.get("severity", "")) == "positive" for f in flags), (
            "Expected positive compliance flag but none found"
        )


def test_transcript_fixture_dataset_summary_exposes_coverage_gaps() -> None:
    bundle = get_domain_bundle()
    summary = summarize_transcript_fixture_dataset(bundle)

    assert summary["fixture_count"] == len(FIXTURE_CASES)
    assert summary["fixture_schema_version"] == 1
    assert summary["fixtures_by_bucket"]["compliance"] >= 3
    assert summary["coverage"]["scenarios"]["missing"] == []
    assert summary["coverage"]["subskills"]["missing"] == []
    assert summary["coverage"]["finish_reasons"]["missing"] == []
    assert summary["coverage"]["compliance_cases"]["missing"] == []


def test_load_transcript_fixture_rejects_missing_expected_required_field(tmp_path: Path) -> None:
    root = tmp_path / "transcripts"
    fixture_dir = root / "good"
    fixture_dir.mkdir(parents=True)
    fixture_path = fixture_dir / "sample_fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "name": "sample_fixture",
                "finish_reason": "manual_finish",
                "scenario_focus_subskills": ["opening"],
                "turns": [{"user_message": "hello", "director_events": []}],
                "expected": {
                    "overall_score_max": 100,
                    "overall_band_one_of": ["strong"],
                },
                "metadata": {
                    "schema_version": 1,
                    "scenario_ids": ["busy_doctor_short_visit"],
                    "compliance_case": "none",
                    "tags": ["smoke"],
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="expected.overall_score_min"):
        load_transcript_fixture(fixture_path, root=root)


def test_transcript_fixture_to_turns_generates_valid_timestamps_beyond_minute_boundary() -> None:
    fixture_turns = [
        {"user_message": f"turn-{index}", "director_events": []}
        for index in range(65)
    ]
    turns = transcript_fixture_to_turns(fixture_turns)

    assert turns[59]["created_at"] == "2026-01-01T00:01:00Z"
    assert turns[64]["created_at"] == "2026-01-01T00:01:05Z"


def test_transcript_fixtures_pass_quality_lint() -> None:
    all_issues = []
    for fixture_path in FIXTURE_CASES:
        fixture = load_transcript_fixture(fixture_path)
        issues = lint_transcript_fixture(fixture)
        for issue in issues:
            all_issues.append(f"{fixture_path.name}: {issue}")

    assert not all_issues, "Fixture quality lint errors found:\n" + "\n".join(all_issues)

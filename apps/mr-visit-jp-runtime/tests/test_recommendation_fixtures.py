from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scenarios.asset_loader import get_domain_bundle
from services.recommendation_engine import (
    build_scenario_recommendations,
    summarize_weakness_clusters,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "recommendations"


def _load_fixture(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"fixture must be object: {path}")
    return payload


FIXTURE_CASES = sorted(FIXTURES_DIR.glob("*.json"))


@pytest.mark.parametrize("fixture_path", FIXTURE_CASES, ids=lambda path: path.stem)
def test_recommendation_fixtures_lock_cluster_and_ranking_regressions(
    fixture_path: Path,
) -> None:
    fixture = _load_fixture(fixture_path)
    expected = fixture["expected"]

    clusters = summarize_weakness_clusters(fixture["recent_history"])
    assert len(clusters) > 0
    assert clusters[0].subskills == expected["dominant_cluster"]["subskills"]
    assert clusters[0].occurrences == expected["dominant_cluster"]["occurrences"]

    bundle = get_domain_bundle()
    expected_ids = expected["recommendation_ids"]
    recommendations = build_scenario_recommendations(
        scenarios=bundle.scenarios,
        current_scenario_id=str(fixture["current_scenario_id"]),
        current_scenario_difficulty=str(fixture["current_scenario_difficulty"]),
        review=fixture["review"],
        recent_history=fixture["recent_history"],
        subskill_trends=fixture["subskill_trends"],
        fallback_subskills=fixture["fallback_subskills"],
        subskill_signals=fixture["subskill_signals"],
        max_items=len(expected_ids),
    )

    assert [item.scenario_id for item in recommendations] == expected_ids
    assert 1 <= len(recommendations) <= 3
    assert recommendations[0].target_subskills == expected["top_target_subskills"]
    if "top_difficulty" in expected:
        assert recommendations[0].difficulty == expected["top_difficulty"]
    for forbidden_top_id in expected.get("forbidden_top_ids", []):
        assert recommendations[0].scenario_id != forbidden_top_id

    top_reason = recommendations[0].reason.lower()
    for fragment in expected["top_reason_fragments"]:
        assert fragment in top_reason

    if "top_evidence_fragments" in expected:
        top_evidence = str(recommendations[0].evidence_source or "").lower()
        for fragment in expected["top_evidence_fragments"]:
            assert fragment in top_evidence

    if "top_stop_condition_fragments" in expected:
        top_stop_condition = str(recommendations[0].stop_condition or "").lower()
        for fragment in expected["top_stop_condition_fragments"]:
            assert fragment in top_stop_condition

    if "top_reason_category" in expected:
        assert recommendations[0].reason_category == expected["top_reason_category"]

    if "top_recommendation_type" in expected:
        assert recommendations[0].recommendation_type == expected["top_recommendation_type"]

    if "top_suggested_repetition_count" in expected:
        assert (
            recommendations[0].suggested_repetition_count
            == expected["top_suggested_repetition_count"]
        )

    for recommendation in recommendations:
        assert recommendation.expected_difficulty in {"easy", "medium", "hard"}
        assert recommendation.suggested_repetition_count >= 1
        assert recommendation.reason_category in {
            "skill",
            "compliance",
            "continuity",
            "mixed",
            "curriculum",
        }

    _assert_recommendation_training_quality(expected, recommendations)


def _assert_recommendation_training_quality(
    expected: dict, recommendations: list
) -> None:
    tq = expected.get("training_quality")
    if not isinstance(tq, dict):
        return

    explainability = tq.get("explainability")
    if explainability == "full":
        for rec in recommendations:
            assert rec.reason, f"Missing reason for {rec.scenario_id}"
            assert rec.evidence_source, f"Missing evidence_source for {rec.scenario_id}"

    if tq.get("require_stop_condition"):
        for rec in recommendations:
            assert rec.stop_condition, f"Missing stop_condition for {rec.scenario_id}"

    if tq.get("require_evidence_source"):
        for rec in recommendations:
            assert rec.evidence_source, f"Missing evidence_source for {rec.scenario_id}"

    if tq.get("require_reason_category"):
        for rec in recommendations:
            assert rec.reason_category in {
                "skill", "compliance", "continuity", "mixed", "curriculum",
            }, f"Invalid reason_category for {rec.scenario_id}: {rec.reason_category}"

    if "max_repetition_of_same_scenario" in tq:
        max_rep = int(tq["max_repetition_of_same_scenario"])
        scenario_counts: dict[str, int] = {}
        for rec in recommendations:
            scenario_counts[rec.scenario_id] = scenario_counts.get(rec.scenario_id, 0) + 1
        for sid, count in scenario_counts.items():
            assert count <= max_rep, (
                f"Scenario {sid} appears {count} times, max allowed {max_rep}"
            )

    forbidden = tq.get("forbidden_unexplained_ids", [])
    if forbidden:
        for rec in recommendations:
            assert rec.scenario_id not in forbidden, (
                f"Forbidden scenario {rec.scenario_id} appeared in recommendations"
            )


def test_recommendations_skip_achieved_scenarios_after_repetition_cap() -> None:
    bundle = get_domain_bundle()
    recommendations = build_scenario_recommendations(
        scenarios=bundle.scenarios,
        current_scenario_id="skeptical_doctor_competitor_pressure",
        current_scenario_difficulty="medium",
        review={
            "overall_score": 48,
            "priority_subskills": ["scientific_delivery", "objection_handling"],
            "diagnosis": {
                "primary": [
                    {
                        "id": "evidence_gap",
                        "summary": "Evidence answers were not specific enough.",
                        "recommendation_focus": ["scientific_delivery", "objection_handling"],
                        "related_subskills": ["scientific_delivery", "objection_handling"],
                    }
                ]
            },
            "subskills": {
                "scientific_delivery": {"score": 1},
                "objection_handling": {"score": 1},
            },
            "compliance_flags": [],
        },
        recent_history=[
            {
                "scenario_id": "cautious_doctor_evidence_check",
                "focus_subskill_scores": {
                    "scientific_delivery": 4.5,
                    "objection_handling": 4.0,
                },
                "focus_subskill_average": 4.25,
                "weak_subskills": [],
                "timestamp": "2026-04-20T10:00:00+00:00",
            },
            {
                "scenario_id": "cautious_doctor_evidence_check",
                "focus_subskill_scores": {
                    "scientific_delivery": 4.0,
                    "objection_handling": 4.5,
                },
                "focus_subskill_average": 4.25,
                "weak_subskills": [],
                "timestamp": "2026-04-22T10:00:00+00:00",
            },
        ],
        subskill_trends={
            "scientific_delivery": "declining",
            "objection_handling": "declining",
        },
        fallback_subskills=["scientific_delivery", "objection_handling"],
        subskill_signals={
            "scientific_delivery": {
                "trend": "declining",
                "rolling_average": 2.3,
                "history_count": 4,
                "last_score": 2.0,
                "mastery_status": "improving",
                "review_status": "focus_now",
            },
            "objection_handling": {
                "trend": "declining",
                "rolling_average": 2.1,
                "history_count": 4,
                "last_score": 2.0,
                "mastery_status": "improving",
                "review_status": "focus_now",
            },
        },
        max_items=3,
    )

    recommendation_ids = [item.scenario_id for item in recommendations]
    assert "cautious_doctor_evidence_check" not in recommendation_ids
    assert recommendation_ids[0] == "formulary_restriction_negotiation"

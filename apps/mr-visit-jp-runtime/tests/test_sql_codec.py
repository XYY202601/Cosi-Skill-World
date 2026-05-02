from __future__ import annotations

from datetime import UTC, datetime

from persistence.sql_codec import (
    build_prompt_context_snapshot_row,
    build_review_row,
    canonical_json_hash,
    reconstruct_prompt_context,
)


def test_canonical_json_hash_is_stable_across_key_order() -> None:
    left = {"profile_id": "alpha", "flags": ["x"], "contracts": {"judge": {"version": 1}}}
    right = {"contracts": {"judge": {"version": 1}}, "flags": ["x"], "profile_id": "alpha"}

    assert canonical_json_hash(left) == canonical_json_hash(right)


def test_prompt_context_snapshot_round_trips_reconstructable_fields() -> None:
    prompt_context = {
        "profile_id": "alpha_baseline_v1",
        "experiment_id": "exp_a",
        "flags": ["canary"],
        "description": "baseline rollout",
        "contracts": {
            "judge": {"contract_id": "judge:v1", "version": 1, "system_prompt": "judge it"},
        },
    }

    row = build_prompt_context_snapshot_row(
        prompt_context,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    reconstructed = reconstruct_prompt_context(
        prompt_profile=row["prompt_profile"],
        experiment_id=row["experiment_id"],
        prompt_flags_json=row["prompt_flags_json"],
        contracts_json=row["contracts_json"],
        summary_json=row["summary_json"],
    )

    assert reconstructed["profile_id"] == "alpha_baseline_v1"
    assert reconstructed["experiment_id"] == "exp_a"
    assert reconstructed["flags"] == ["canary"]
    assert reconstructed["description"] == "baseline rollout"
    assert reconstructed["contracts"]["judge"]["version"] == 1


def test_build_review_row_extracts_searchable_review_fields() -> None:
    review = {
        "overall_score": 81,
        "overall_band": "strong",
        "priority_subskills": ["opening", "profiling"],
        "compliance_flags": [
            {"rule_id": "ae_report", "severity": "high"},
            {"rule_id": "fair_balance", "severity": "medium"},
        ],
        "meta": {
            "artifact_sources": {"judge": "model"},
            "fallback_reasons": ["model_coach_failed"],
        },
    }

    row = build_review_row(
        session_id="sess_123",
        prompt_context_id=42,
        prompt_context={"profile_id": "alpha_baseline_v1", "contracts": {}},
        review=review,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert row["session_id"] == "sess_123"
    assert row["prompt_context_id"] == 42
    assert row["overall_score"] == 81
    assert row["overall_band"] == "strong"
    assert row["priority_subskills"] == ["opening", "profiling"]
    assert row["compliance_rule_ids"] == ["ae_report", "fair_balance"]
    assert row["compliance_severities"] == ["high", "medium"]
    assert row["artifact_sources_json"] == {"judge": "model"}
    assert row["fallback_reasons_json"] == ["model_coach_failed"]

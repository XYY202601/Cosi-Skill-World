from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scenarios import asset_loader
from scenarios.asset_loader import DomainAssetError


def _scenario_schema() -> dict[str, object]:
    return asset_loader._read_json(
        asset_loader.SCHEMAS_DIR / "mr_scenario.schema.json"
    )


def _valid_scenario_payload() -> dict[str, object]:
    return {
        "id": "playbook_test_scenario",
        "title": "Playbook Test Scenario",
        "difficulty": "medium",
        "focus_subskills": ["opening", "need_discovery"],
        "doctor_persona_id": "test_persona",
        "constraints": {"max_turns": 10},
        "success_criteria": [
            "recovers_after_weak_opening",
            "identifies_one_clinical_need",
        ],
        "failure_patterns": [
            "keeps_pitching_after_interest_drop",
            "fails_to_prove_relevance_quickly",
            "asks_generic_questions_without_need_signal",
        ],
        "playbook": {
            "learning_objective": "Recover interest with a specific question and clear relevance.",
            "target_subskills": ["opening", "need_discovery"],
            "expected_flow": [
                "MR opens briefly and detects low interest.",
                "MR acknowledges low relevance and pivots.",
                "MR asks one concrete discovery question.",
            ],
            "key_discovery_questions": [
                "What is the biggest challenge in this patient segment right now?"
            ],
            "acceptable_evidence_moves": [
                "I can keep this to one practical data point for the patient group you care about."
            ],
            "common_failure_patterns": [
                "Continues the generic script after the doctor disengages.",
                "Adds apology without clarifying relevance.",
                "Misses the chance to ask one targeted question.",
            ],
            "recovery_moves": [
                "Acknowledge the weak opening and pivot to one patient-specific question."
            ],
            "completion_signals": [
                "Doctor acknowledges a specific reason to continue the discussion."
            ],
            "positive_example_moves": [
                "If I could focus on one patient type that still feels difficult to manage, would that be useful?"
            ],
            "negative_example_moves": [
                "Let me keep going with the same slide deck for a few more minutes."
            ],
        },
    }


def _write_scenario_file(
    scenarios_dir: Path,
    payload: dict[str, object],
    *,
    filename: str = "scenario.yaml",
) -> None:
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    (scenarios_dir / filename).write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def test_real_mr_scenarios_meet_playbook_quality_gates() -> None:
    bundle = asset_loader.load_domain_bundle()

    assert len(bundle.scenarios) == 8
    for scenario in bundle.scenarios.values():
        assert scenario.playbook is not None
        assert scenario.playbook.learning_objective
        assert len(scenario.playbook.target_subskills) >= 2
        assert set(scenario.playbook.target_subskills) == set(scenario.focus_subskills)
        assert len(scenario.playbook.common_failure_patterns) >= 3
        assert len(scenario.playbook.key_discovery_questions) >= 1
        assert len(scenario.playbook.acceptable_evidence_moves) >= 1
        assert len(scenario.playbook.recovery_moves) >= 1
        assert len(scenario.playbook.completion_signals) >= 1
        assert len(scenario.playbook.positive_example_moves) >= 1
        assert len(scenario.playbook.negative_example_moves) >= 1


def test_load_scenarios_rejects_missing_playbook(tmp_path: Path) -> None:
    payload = _valid_scenario_payload()
    payload.pop("playbook")
    scenarios_dir = tmp_path / "scenarios"
    _write_scenario_file(scenarios_dir, payload)

    with pytest.raises(DomainAssetError, match="required property"):
        asset_loader._load_scenarios(
            {"test_persona": {"id": "test_persona"}},
            _scenario_schema(),
            {"opening", "need_discovery"},
            scenarios_dir=scenarios_dir,
        )


def test_load_scenarios_rejects_playbook_with_too_few_target_subskills(
    tmp_path: Path,
) -> None:
    payload = _valid_scenario_payload()
    payload["playbook"]["target_subskills"] = ["opening"]
    scenarios_dir = tmp_path / "scenarios"
    _write_scenario_file(scenarios_dir, payload)

    with pytest.raises(DomainAssetError, match="playbook.target_subskills"):
        asset_loader._load_scenarios(
            {"test_persona": {"id": "test_persona"}},
            _scenario_schema(),
            {"opening", "need_discovery"},
            scenarios_dir=scenarios_dir,
        )


def test_load_scenarios_rejects_playbook_target_subskill_drift(tmp_path: Path) -> None:
    payload = _valid_scenario_payload()
    payload["playbook"]["target_subskills"] = ["opening", "profiling"]
    scenarios_dir = tmp_path / "scenarios"
    _write_scenario_file(scenarios_dir, payload)

    with pytest.raises(DomainAssetError, match="target_subskills must match focus_subskills"):
        asset_loader._load_scenarios(
            {"test_persona": {"id": "test_persona"}},
            _scenario_schema(),
            {"opening", "need_discovery", "profiling"},
            scenarios_dir=scenarios_dir,
        )


def test_load_scenarios_rejects_compliance_sensitive_playbook_without_recovery_move(
    tmp_path: Path,
) -> None:
    payload = _valid_scenario_payload()
    payload["id"] = "adverse_event_followup_required"
    payload["title"] = "Adverse Event Follow-up Required"
    payload["focus_subskills"] = ["profiling", "closing_followup"]
    payload["success_criteria"] = [
        "captures_required_information",
        "performs_correct_escalation_statement",
    ]
    payload["failure_patterns"] = [
        "continues_promotional_talk_after_event_report",
        "fails_to_state_internal_followup_process",
        "gives_speculative_medical_advice",
    ]
    payload["playbook"]["learning_objective"] = (
        "Handle an adverse event report with compliant escalation."
    )
    payload["playbook"]["target_subskills"] = ["profiling", "closing_followup"]
    payload["playbook"]["expected_flow"] = [
        "Doctor reports a possible adverse event.",
        "MR stops promotion and captures core details.",
        "MR explains the reporting and escalation path.",
    ]
    payload["playbook"]["recovery_moves"] = [
        "Acknowledge the concern and continue the conversation carefully."
    ]

    scenarios_dir = tmp_path / "scenarios"
    _write_scenario_file(scenarios_dir, payload)

    with pytest.raises(
        DomainAssetError,
        match="compliance-specific recovery or escalation move",
    ):
        asset_loader._load_scenarios(
            {"test_persona": {"id": "test_persona"}},
            _scenario_schema(),
            {"profiling", "closing_followup"},
            scenarios_dir=scenarios_dir,
        )

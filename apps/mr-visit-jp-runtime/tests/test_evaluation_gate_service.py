from __future__ import annotations

from pathlib import Path

from persistence.file_session_store import FileSessionStore
from providers import load_runtime_prompt_context, summarize_prompt_context
from scenarios.asset_loader import get_domain_bundle
from services.evaluation_gate_service import EvaluationGateService
from services.evaluation_fixture_dataset import list_transcript_fixture_paths


def _session_payload(
    *,
    session_id: str,
    prompt_context: dict[str, object],
    overall_score: int,
    overall_band: str,
    fallback_reasons: list[str] | None = None,
    high_risk: bool = False,
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "scenario_id": "busy_doctor_short_visit",
        "learner_id": f"learner_{session_id}",
        "status": "finalized",
        "updated_at": "2026-04-23T00:00:00+00:00",
        "prompt_context": prompt_context,
        "review": {
            "overall_score": overall_score,
            "overall_band": overall_band,
            "compliance_flags": (
                [{"rule_id": "risk_case", "severity": "high", "summary": "risk"}] if high_risk else []
            ),
            "meta": {
                "prompting": summarize_prompt_context(prompt_context),
                "fallback_reasons": list(fallback_reasons or []),
                "artifact_sources": {
                    "judge": "model" if not fallback_reasons else "rule",
                    "coach": "model" if not fallback_reasons else "rule",
                    "compliance": "model" if not fallback_reasons else "rule",
                },
            },
        },
    }


def test_evaluation_gate_service_reports_offline_and_online_gate_status(tmp_path: Path) -> None:
    bundle = get_domain_bundle()
    session_store = FileSessionStore(tmp_path / "sessions")

    baseline_context = load_runtime_prompt_context(profile_id="alpha_baseline_v1")
    canary_context = load_runtime_prompt_context(
        profile_id="alpha_coach_concise_v1",
        experiment_id="coach-canary-1",
    )

    session_store.create(
        "sess_gate_001",
        _session_payload(
            session_id="sess_gate_001",
            prompt_context=baseline_context,
            overall_score=78,
            overall_band="strong",
        ),
    )
    session_store.create(
        "sess_gate_002",
        _session_payload(
            session_id="sess_gate_002",
            prompt_context=baseline_context,
            overall_score=66,
            overall_band="functional",
        ),
    )
    session_store.create(
        "sess_gate_003",
        _session_payload(
            session_id="sess_gate_003",
            prompt_context=canary_context,
            overall_score=82,
            overall_band="strong",
        ),
    )

    service = EvaluationGateService(
        domain_bundle=bundle,
        session_store=session_store,
        requested_prompt_context=baseline_context,
    )

    report = service.build_report()
    assert report["domain_id"] == "mr_visit_jp"
    assert report["default_profile_id"] == "alpha_baseline_v1"
    assert report["rollout"]["status"] == "active"
    assert report["rollout"]["effective"]["profile_id"] == "alpha_baseline_v1"
    assert report["offline_dataset"]["fixture_count"] >= 10
    assert report["offline_dataset"]["coverage"]["scenarios"]["missing"] == []
    assert report["offline_dataset"]["coverage"]["subskills"]["missing"] == []
    assert service.effective_prompt_context["profile_id"] == "alpha_baseline_v1"

    offline_by_profile = {
        item["profile_id"]: item
        for item in report["offline_gates"]
    }
    assert offline_by_profile["alpha_baseline_v1"]["status"] == "pass"
    assert offline_by_profile["alpha_coach_concise_v1"]["status"] == "pass"
    assert offline_by_profile["alpha_coach_concise_v1"]["contract_versions"]["coach"] == 2
    assert offline_by_profile["alpha_coach_concise_v1"]["output_requirement_counts"]["coach"] >= 6
    first_fixture = offline_by_profile["alpha_baseline_v1"]["fixture_results"][0]
    assert first_fixture["fixture_path"]
    assert first_fixture["bucket"]
    assert isinstance(first_fixture["scenario_ids"], list)
    assert isinstance(first_fixture["focus_subskills"], list)
    assert isinstance(first_fixture["tags"], list)

    online_by_key = {
        (item["profile_id"], item["experiment_id"]): item
        for item in report["online_gates"]
    }
    baseline_gate = online_by_key[("alpha_baseline_v1", None)]
    assert baseline_gate["status"] == "pass"
    assert baseline_gate["sample_size"] == 2
    assert baseline_gate["metrics"]["average_overall_score"] >= 50
    assert baseline_gate["metrics"]["fallback_rate"] == 0.0

    canary_gate = online_by_key[("alpha_coach_concise_v1", "coach-canary-1")]
    assert canary_gate["status"] == "insufficient_data"
    assert canary_gate["sample_size"] == 1


def test_evaluation_gate_service_blocks_unpromoted_rollout_and_falls_back_to_stable(
    tmp_path: Path,
) -> None:
    bundle = get_domain_bundle()
    session_store = FileSessionStore(tmp_path / "sessions")

    baseline_context = load_runtime_prompt_context(profile_id="alpha_baseline_v1")
    canary_context = load_runtime_prompt_context(
        profile_id="alpha_coach_concise_v1",
        experiment_id="coach-canary-1",
    )

    session_store.create(
        "sess_gate_block_001",
        _session_payload(
            session_id="sess_gate_block_001",
            prompt_context=baseline_context,
            overall_score=74,
            overall_band="strong",
        ),
    )
    session_store.create(
        "sess_gate_block_002",
        _session_payload(
            session_id="sess_gate_block_002",
            prompt_context=baseline_context,
            overall_score=62,
            overall_band="functional",
        ),
    )
    session_store.create(
        "sess_gate_block_003",
        _session_payload(
            session_id="sess_gate_block_003",
            prompt_context=canary_context,
            overall_score=81,
            overall_band="strong",
        ),
    )

    service = EvaluationGateService(
        domain_bundle=bundle,
        session_store=session_store,
        requested_prompt_context=canary_context,
    )

    report = service.build_report()
    assert report["default_profile_id"] == "alpha_baseline_v1"
    assert report["rollout"]["status"] == "blocked"
    assert report["rollout"]["requested"]["profile_id"] == "alpha_coach_concise_v1"
    assert report["rollout"]["requested"]["experiment_id"] == "coach-canary-1"
    assert report["rollout"]["effective"]["profile_id"] == "alpha_baseline_v1"
    assert service.effective_prompt_context["profile_id"] == "alpha_baseline_v1"
    assert service.effective_prompt_context["experiment_id"] is None


def test_evaluation_gate_service_promotes_rollout_when_candidate_passes_online_gate(
    tmp_path: Path,
) -> None:
    bundle = get_domain_bundle()
    session_store = FileSessionStore(tmp_path / "sessions")

    canary_context = load_runtime_prompt_context(
        profile_id="alpha_coach_concise_v1",
        experiment_id="coach-canary-1",
    )

    session_store.create(
        "sess_gate_promote_001",
        _session_payload(
            session_id="sess_gate_promote_001",
            prompt_context=canary_context,
            overall_score=76,
            overall_band="strong",
        ),
    )
    session_store.create(
        "sess_gate_promote_002",
        _session_payload(
            session_id="sess_gate_promote_002",
            prompt_context=canary_context,
            overall_score=69,
            overall_band="functional",
        ),
    )

    service = EvaluationGateService(
        domain_bundle=bundle,
        session_store=session_store,
        requested_prompt_context=canary_context,
    )

    report = service.build_report()
    assert report["default_profile_id"] == "alpha_coach_concise_v1"
    assert report["rollout"]["status"] == "promoted"
    assert report["rollout"]["effective"]["profile_id"] == "alpha_coach_concise_v1"
    assert report["rollout"]["effective"]["experiment_id"] == "coach-canary-1"
    assert service.effective_prompt_context["profile_id"] == "alpha_coach_concise_v1"
    assert service.effective_prompt_context["experiment_id"] == "coach-canary-1"


def test_evaluation_gate_service_allows_blocked_rollout_with_explicit_override(
    tmp_path: Path,
) -> None:
    bundle = get_domain_bundle()
    session_store = FileSessionStore(tmp_path / "sessions")

    baseline_context = load_runtime_prompt_context(profile_id="alpha_baseline_v1")
    canary_context = load_runtime_prompt_context(
        profile_id="alpha_coach_concise_v1",
        experiment_id="coach-canary-1",
    )

    session_store.create(
        "sess_gate_override_001",
        _session_payload(
            session_id="sess_gate_override_001",
            prompt_context=baseline_context,
            overall_score=72,
            overall_band="strong",
        ),
    )
    session_store.create(
        "sess_gate_override_002",
        _session_payload(
            session_id="sess_gate_override_002",
            prompt_context=baseline_context,
            overall_score=60,
            overall_band="functional",
        ),
    )
    session_store.create(
        "sess_gate_override_003",
        _session_payload(
            session_id="sess_gate_override_003",
            prompt_context=canary_context,
            overall_score=79,
            overall_band="strong",
        ),
    )

    service = EvaluationGateService(
        domain_bundle=bundle,
        session_store=session_store,
        requested_prompt_context=canary_context,
        allow_blocked_rollout=True,
    )

    report = service.build_report()
    assert report["default_profile_id"] == "alpha_coach_concise_v1"
    assert report["rollout"]["status"] == "override_allowed"
    assert report["rollout"]["allow_blocked_rollout"] is True
    assert report["rollout"]["effective"]["profile_id"] == "alpha_coach_concise_v1"
    assert service.effective_prompt_context["profile_id"] == "alpha_coach_concise_v1"


def test_evaluation_gate_service_caches_offline_fixture_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle = get_domain_bundle()
    session_store = FileSessionStore(tmp_path / "sessions")
    baseline_context = load_runtime_prompt_context(profile_id="alpha_baseline_v1")
    fixture_count = len(list_transcript_fixture_paths())

    original_evaluate_fixture = EvaluationGateService._evaluate_fixture
    invocation_count = {"value": 0}

    def _counting_evaluate_fixture(self, fixture_path: Path) -> dict[str, object]:
        invocation_count["value"] += 1
        return original_evaluate_fixture(self, fixture_path)

    monkeypatch.setattr(
        EvaluationGateService,
        "_evaluate_fixture",
        _counting_evaluate_fixture,
    )

    service = EvaluationGateService(
        domain_bundle=bundle,
        session_store=session_store,
        requested_prompt_context=baseline_context,
    )
    assert invocation_count["value"] == fixture_count

    _ = service.build_report()
    _ = service.build_report()
    assert invocation_count["value"] == fixture_count

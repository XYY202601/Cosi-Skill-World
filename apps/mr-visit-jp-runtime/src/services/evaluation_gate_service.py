from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from evaluation.review_builder import build_runtime_review
from persistence.interfaces import SessionStore
from providers import (
    list_prompt_profile_ids,
    load_runtime_prompt_context,
    summarize_prompt_context,
)
from scenarios.asset_loader import DomainBundle
from services.evaluation_fixture_dataset import (
    list_transcript_fixture_paths,
    load_transcript_fixture,
    summarize_transcript_fixture,
    summarize_transcript_fixture_dataset,
    transcript_fixture_to_turns,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
PROMPT_GATES_PATH = REPO_ROOT / "domains" / "mr_visit_jp" / "prompts" / "evaluation_gates.yaml"
HIGH_RISK_SEVERITIES = {"high", "critical"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    return default


def _load_gate_config() -> dict[str, Any]:
    with PROMPT_GATES_PATH.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"gate config must be object: {PROMPT_GATES_PATH}")

    offline = payload.get("offline", {})
    online = payload.get("online", {})
    if not isinstance(offline, dict):
        raise ValueError("offline gate config must be an object")
    if not isinstance(online, dict):
        raise ValueError("online gate config must be an object")

    offline_profiles = offline.get("profiles", {})
    if not isinstance(offline_profiles, dict):
        raise ValueError("offline.profiles must be an object")

    online_default = online.get("default", {})
    if not isinstance(online_default, dict):
        raise ValueError("online.default must be an object")

    return payload


def _fixture_passes(review: dict[str, Any], expected: dict[str, Any]) -> bool:
    overall_score = int(review.get("overall_score", 0))
    if overall_score < int(expected["overall_score_min"]):
        return False
    if overall_score > int(expected["overall_score_max"]):
        return False
    if review.get("overall_band") not in list(expected["overall_band_one_of"]):
        return False

    diagnosis_ids = {
        item["id"]
        for item in review.get("diagnosis", {}).get("primary", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for required_diagnosis_id in expected.get("required_diagnosis_ids", []):
        if required_diagnosis_id not in diagnosis_ids:
            return False
    for forbidden_diagnosis_id in expected.get("forbidden_diagnosis_ids", []):
        if forbidden_diagnosis_id in diagnosis_ids:
            return False

    compliance_rule_ids = {
        item["rule_id"]
        for item in review.get("compliance_flags", [])
        if isinstance(item, dict) and isinstance(item.get("rule_id"), str)
    }
    for required_rule_id in expected.get("required_compliance_rule_ids", []):
        if required_rule_id not in compliance_rule_ids:
            return False
    for forbidden_rule_id in expected.get("forbidden_compliance_rule_ids", []):
        if forbidden_rule_id in compliance_rule_ids:
            return False

    severities = {
        str(item.get("severity", ""))
        for item in review.get("compliance_flags", [])
        if isinstance(item, dict)
    }
    for required_severity in expected.get("required_compliance_severities", []):
        if required_severity not in severities:
            return False
    for forbidden_severity in expected.get("forbidden_compliance_severities", []):
        if forbidden_severity in severities:
            return False

    subskills = review.get("subskills", {})
    required_subskill_score_min = expected.get("required_subskill_score_min", {})
    if isinstance(required_subskill_score_min, dict):
        for subskill_id, min_score in required_subskill_score_min.items():
            subskill = subskills.get(subskill_id, {})
            if int(subskill.get("score", 0)) < int(min_score):
                return False

    required_subskill_score_max = expected.get("required_subskill_score_max", {})
    if isinstance(required_subskill_score_max, dict):
        for subskill_id, max_score in required_subskill_score_max.items():
            subskill = subskills.get(subskill_id, {})
            if int(subskill.get("score", 0)) > int(max_score):
                return False

    return True


class EvaluationGateService:
    def __init__(
        self,
        *,
        domain_bundle: DomainBundle,
        session_store: SessionStore,
        requested_prompt_context: dict[str, Any],
        allow_blocked_rollout: bool = False,
    ) -> None:
        self._bundle = domain_bundle
        self._session_store = session_store
        self._requested_prompt_context = deepcopy(requested_prompt_context)
        self._requested_prompt_summary = summarize_prompt_context(self._requested_prompt_context)
        self._stable_prompt_context = load_runtime_prompt_context()
        self._stable_prompt_summary = summarize_prompt_context(self._stable_prompt_context)
        self._allow_blocked_rollout = allow_blocked_rollout
        self._gate_config = _load_gate_config()
        self._fixture_paths = list_transcript_fixture_paths()
        self._fixture_dataset = summarize_transcript_fixture_dataset(self._bundle)
        self._offline_gates_cache: list[dict[str, Any]] | None = None
        self._rollout_decision = self._resolve_rollout_decision()
        self._effective_prompt_context = deepcopy(
            self._rollout_decision["effective_prompt_context"]
        )
        self._effective_prompt_summary = summarize_prompt_context(self._effective_prompt_context)

    @property
    def effective_prompt_context(self) -> dict[str, Any]:
        return deepcopy(self._effective_prompt_context)

    def build_report(self) -> dict[str, Any]:
        return {
            "domain_id": str(self._bundle.manifest["id"]),
            "default_profile_id": self._effective_prompt_summary["profile_id"],
            "rollout": self._serialize_rollout_decision(),
            "offline_dataset": self._serialize_offline_dataset(),
            "offline_gates": self._build_offline_gates(),
            "online_gates": self._build_online_gates(),
        }

    def _serialize_offline_dataset(self) -> dict[str, Any]:
        coverage = self._fixture_dataset["coverage"]
        return {
            "fixture_schema_version": int(self._fixture_dataset["fixture_schema_version"]),
            "fixture_count": int(self._fixture_dataset["fixture_count"]),
            "fixtures_by_bucket": dict(self._fixture_dataset["fixtures_by_bucket"]),
            "coverage": {
                "scenarios": deepcopy(coverage["scenarios"]),
                "subskills": deepcopy(coverage["subskills"]),
                "compliance_cases": deepcopy(coverage["compliance_cases"]),
                "finish_reasons": deepcopy(coverage["finish_reasons"]),
            },
        }

    def _serialize_rollout_decision(self) -> dict[str, Any]:
        return {
            "status": self._rollout_decision["status"],
            "requested": deepcopy(self._rollout_decision["requested"]),
            "effective": deepcopy(self._rollout_decision["effective"]),
            "stable_profile_id": self._rollout_decision["stable_profile_id"],
            "allow_blocked_rollout": self._rollout_decision["allow_blocked_rollout"],
            "checks": deepcopy(self._rollout_decision["checks"]),
        }

    def _evaluate_fixture(self, fixture_path: Path) -> dict[str, Any]:
        fixture = load_transcript_fixture(fixture_path)
        expected = fixture["expected"]
        turns = transcript_fixture_to_turns(fixture["turns"])
        fixture_summary = summarize_transcript_fixture(fixture_path, fixture)

        subskill_weights = {
            subskill_id: float(payload["weight"])
            for subskill_id, payload in self._bundle.skill_model["subskills"].items()
        }
        review = build_runtime_review(
            turns=turns,
            turn_count=len(turns),
            finish_reason=str(fixture.get("finish_reason", "manual_finish")),
            scenario_focus_subskills=list(fixture["scenario_focus_subskills"]),
            subskill_weights=subskill_weights,
            skill_model=self._bundle.skill_model,
            diagnosis_types=self._bundle.diagnosis_types,
            compliance_rules=self._bundle.compliance_rules,
            score_schema=self._bundle.score_schema,
            judge_review_schema=self._bundle.judge_review_schema,
            coach_feedback_schema=self._bundle.coach_feedback_schema,
            compliance_flags_schema=self._bundle.compliance_flags_schema,
            model_artifacts=None,
            model_error=None,
            continuity_context=fixture.get("continuity_context"),
        )

        passed = _fixture_passes(review, expected)
        return {
            **fixture_summary,
            "passed": passed,
            "overall_score": int(review.get("overall_score", 0)),
            "overall_band": str(review.get("overall_band", "unknown")),
        }

    def _build_offline_gates(self) -> list[dict[str, Any]]:
        if self._offline_gates_cache is not None:
            return deepcopy(self._offline_gates_cache)

        offline_cfg = self._gate_config["offline"]
        required_fixture_pass_rate = _safe_float(offline_cfg.get("required_fixture_pass_rate"), 1.0)
        fixture_results = [self._evaluate_fixture(path) for path in self._fixture_paths]
        fixture_pass_count = sum(1 for item in fixture_results if item["passed"])
        fixture_pass_rate = (
            fixture_pass_count / len(fixture_results) if fixture_results else 0.0
        )

        gates: list[dict[str, Any]] = []
        for profile_id in list_prompt_profile_ids():
            prompt_context = load_runtime_prompt_context(profile_id=profile_id)
            contracts = prompt_context.get("contracts", {})
            profile_rules = offline_cfg.get("profiles", {}).get(profile_id, {})
            required_versions = (
                profile_rules.get("required_contract_versions", {})
                if isinstance(profile_rules, dict)
                else {}
            )
            min_output_requirements = (
                profile_rules.get("min_output_requirements", {})
                if isinstance(profile_rules, dict)
                else {}
            )

            contract_versions = {
                role: int(contract.get("version", 0))
                for role, contract in contracts.items()
                if isinstance(contract, dict)
            }
            output_requirement_counts = {
                role: len(contract.get("output_requirements", []))
                for role, contract in contracts.items()
                if isinstance(contract, dict)
            }

            checks = [
                {
                    "name": "fixture_pass_rate",
                    "passed": fixture_pass_rate >= required_fixture_pass_rate,
                    "detail": (
                        f"{fixture_pass_count}/{len(self._fixture_paths)} fixtures passed "
                        f"(required {required_fixture_pass_rate:.2f})"
                    ),
                }
            ]
            for role, expected_version in required_versions.items():
                actual_version = contract_versions.get(role, 0)
                checks.append(
                    {
                        "name": f"{role}_contract_version",
                        "passed": actual_version == int(expected_version),
                        "detail": f"expected v{expected_version}, got v{actual_version}",
                    }
                )
            for role, minimum_count in min_output_requirements.items():
                actual_count = output_requirement_counts.get(role, 0)
                checks.append(
                    {
                        "name": f"{role}_output_requirements",
                        "passed": actual_count >= int(minimum_count),
                        "detail": f"required >= {minimum_count}, got {actual_count}",
                    }
                )

            status = "pass" if all(check["passed"] for check in checks) else "fail"
            gates.append(
                {
                    "profile_id": profile_id,
                    "status": status,
                    "fixture_pass_rate": round(fixture_pass_rate, 4),
                    "fixture_results": deepcopy(fixture_results),
                    "contract_versions": contract_versions,
                    "output_requirement_counts": output_requirement_counts,
                    "checks": checks,
                }
            )

        self._offline_gates_cache = gates
        return deepcopy(gates)

    def _build_offline_gate_index(self) -> dict[str, dict[str, Any]]:
        return {
            str(item["profile_id"]): item
            for item in self._build_offline_gates()
        }

    def _build_online_gates(self) -> list[dict[str, Any]]:
        online_default_cfg = self._gate_config["online"]["default"]
        groups: dict[tuple[str, str | None], dict[str, Any]] = {}

        for session_payload in self._session_store.list_all():
            if str(session_payload.get("status", "")) != "finalized":
                continue

            review = session_payload.get("review")
            if not isinstance(review, dict):
                continue

            review_meta = review.get("meta", {})
            prompting = (
                review_meta.get("prompting")
                if isinstance(review_meta, dict)
                else None
            )
            summary = (
                prompting
                if isinstance(prompting, dict)
                else summarize_prompt_context(session_payload.get("prompt_context"))
            )
            profile_id = str(summary.get("profile_id", "unknown"))
            experiment_id = summary.get("experiment_id")
            group = groups.setdefault(
                (profile_id, experiment_id),
                {
                    "profile_id": profile_id,
                    "experiment_id": experiment_id,
                    "sample_size": 0,
                    "score_total": 0.0,
                    "strong_or_better_count": 0,
                    "high_risk_count": 0,
                    "fallback_count": 0,
                    "updated_at": "",
                },
            )

            group["sample_size"] += 1
            group["score_total"] += _safe_float(review.get("overall_score"), 0.0)
            if str(review.get("overall_band", "")) in {"strong", "excellent"}:
                group["strong_or_better_count"] += 1

            compliance_flags = review.get("compliance_flags", [])
            if isinstance(compliance_flags, list) and any(
                isinstance(flag, dict)
                and str(flag.get("severity", "")).lower() in HIGH_RISK_SEVERITIES
                for flag in compliance_flags
            ):
                group["high_risk_count"] += 1

            fallback_reasons = (
                review_meta.get("fallback_reasons", [])
                if isinstance(review_meta, dict)
                else []
            )
            artifact_sources = (
                review_meta.get("artifact_sources", {})
                if isinstance(review_meta, dict)
                else {}
            )
            used_fallback = bool(fallback_reasons) or any(
                str(source) != "model" for source in artifact_sources.values()
            )
            if used_fallback:
                group["fallback_count"] += 1

            group["updated_at"] = str(session_payload.get("updated_at", "")) or group["updated_at"]

        active_prompt_summary = getattr(
            self,
            "_effective_prompt_summary",
            self._requested_prompt_summary,
        )
        default_group_key = (
            str(active_prompt_summary["profile_id"]),
            active_prompt_summary.get("experiment_id"),
        )
        groups.setdefault(
            default_group_key,
            {
                "profile_id": default_group_key[0],
                "experiment_id": default_group_key[1],
                "sample_size": 0,
                "score_total": 0.0,
                "strong_or_better_count": 0,
                "high_risk_count": 0,
                "fallback_count": 0,
                "updated_at": "",
            },
        )

        gates: list[dict[str, Any]] = []
        for key in sorted(groups.keys(), key=lambda item: (item[0], item[1] or "")):
            group = groups[key]
            sample_size = int(group["sample_size"])
            average_overall_score = (
                group["score_total"] / sample_size if sample_size else 0.0
            )
            strong_or_better_rate = (
                group["strong_or_better_count"] / sample_size if sample_size else 0.0
            )
            high_risk_rate = group["high_risk_count"] / sample_size if sample_size else 0.0
            fallback_rate = group["fallback_count"] / sample_size if sample_size else 0.0

            thresholds = {
                "min_sessions": _safe_int(online_default_cfg.get("min_sessions"), 0),
                "min_average_overall_score": _safe_float(
                    online_default_cfg.get("min_average_overall_score"),
                    0.0,
                ),
                "max_high_risk_rate": _safe_float(
                    online_default_cfg.get("max_high_risk_rate"),
                    1.0,
                ),
                "max_fallback_rate": _safe_float(
                    online_default_cfg.get("max_fallback_rate"),
                    1.0,
                ),
            }

            checks = [
                {
                    "name": "min_sessions",
                    "passed": sample_size >= thresholds["min_sessions"],
                    "detail": f"required >= {thresholds['min_sessions']}, got {sample_size}",
                }
            ]

            if sample_size >= thresholds["min_sessions"]:
                checks.extend(
                    [
                        {
                            "name": "average_overall_score",
                            "passed": average_overall_score
                            >= thresholds["min_average_overall_score"],
                            "detail": (
                                f"required >= {thresholds['min_average_overall_score']}, "
                                f"got {average_overall_score:.2f}"
                            ),
                        },
                        {
                            "name": "high_risk_rate",
                            "passed": high_risk_rate <= thresholds["max_high_risk_rate"],
                            "detail": (
                                f"required <= {thresholds['max_high_risk_rate']}, "
                                f"got {high_risk_rate:.2f}"
                            ),
                        },
                        {
                            "name": "fallback_rate",
                            "passed": fallback_rate <= thresholds["max_fallback_rate"],
                            "detail": (
                                f"required <= {thresholds['max_fallback_rate']}, "
                                f"got {fallback_rate:.2f}"
                            ),
                        },
                    ]
                )

            if sample_size < thresholds["min_sessions"]:
                status = "insufficient_data"
            else:
                status = "pass" if all(check["passed"] for check in checks) else "fail"

            gates.append(
                {
                    "profile_id": group["profile_id"],
                    "experiment_id": group["experiment_id"],
                    "status": status,
                    "sample_size": sample_size,
                    "metrics": {
                        "average_overall_score": round(average_overall_score, 2),
                        "strong_or_better_rate": round(strong_or_better_rate, 4),
                        "high_risk_rate": round(high_risk_rate, 4),
                        "fallback_rate": round(fallback_rate, 4),
                    },
                    "thresholds": thresholds,
                    "checks": checks,
                    "updated_at": group["updated_at"],
                }
            )

        return gates

    def _build_online_gate_index(self) -> dict[tuple[str, str | None], dict[str, Any]]:
        return {
            (str(item["profile_id"]), item.get("experiment_id")): item
            for item in self._build_online_gates()
        }

    def _build_synthetic_online_gate(
        self,
        *,
        profile_id: str,
        experiment_id: str | None,
    ) -> dict[str, Any]:
        thresholds = {
            "min_sessions": _safe_int(self._gate_config["online"]["default"].get("min_sessions"), 0),
            "min_average_overall_score": _safe_float(
                self._gate_config["online"]["default"].get("min_average_overall_score"),
                0.0,
            ),
            "max_high_risk_rate": _safe_float(
                self._gate_config["online"]["default"].get("max_high_risk_rate"),
                1.0,
            ),
            "max_fallback_rate": _safe_float(
                self._gate_config["online"]["default"].get("max_fallback_rate"),
                1.0,
            ),
        }
        return {
            "profile_id": profile_id,
            "experiment_id": experiment_id,
            "status": "insufficient_data",
            "sample_size": 0,
            "metrics": {
                "average_overall_score": 0.0,
                "strong_or_better_rate": 0.0,
                "high_risk_rate": 0.0,
                "fallback_rate": 0.0,
            },
            "thresholds": thresholds,
            "checks": [
                {
                    "name": "min_sessions",
                    "passed": False,
                    "detail": f"required >= {thresholds['min_sessions']}, got 0",
                }
            ],
            "updated_at": "",
        }

    def _resolve_rollout_decision(self) -> dict[str, Any]:
        offline_by_profile = self._build_offline_gate_index()
        online_by_key = self._build_online_gate_index()

        requested_profile_id = str(self._requested_prompt_summary["profile_id"])
        requested_experiment_id = self._requested_prompt_summary.get("experiment_id")
        stable_profile_id = str(self._stable_prompt_summary["profile_id"])
        requires_online_gate = (
            requested_profile_id != stable_profile_id
            or requested_experiment_id is not None
        )

        requested_offline_gate = offline_by_profile.get(requested_profile_id)
        if requested_offline_gate is None:
            raise RuntimeError(f"Missing offline gate result for prompt profile `{requested_profile_id}`")

        requested_offline_pass = str(requested_offline_gate["status"]) == "pass"
        checks = [
            {
                "name": "requested_offline_gate",
                "passed": requested_offline_pass,
                "detail": (
                    f"profile `{requested_profile_id}` offline gate status is "
                    f"`{requested_offline_gate['status']}`"
                ),
            }
        ]

        if requires_online_gate:
            requested_online_gate = online_by_key.get((requested_profile_id, requested_experiment_id))
            if requested_online_gate is None:
                requested_online_gate = self._build_synthetic_online_gate(
                    profile_id=requested_profile_id,
                    experiment_id=requested_experiment_id,
                )
            requested_online_pass = str(requested_online_gate["status"]) == "pass"
            checks.append(
                {
                    "name": "requested_online_gate",
                    "passed": requested_online_pass,
                    "detail": (
                        f"profile `{requested_profile_id}` experiment "
                        f"`{requested_experiment_id or 'default'}` online gate status is "
                        f"`{requested_online_gate['status']}`"
                    ),
                }
            )
        else:
            requested_online_pass = True
            checks.append(
                {
                    "name": "requested_online_gate",
                    "passed": True,
                    "detail": "online gate is not required for the stable default prompt profile",
                }
            )

        rollout_allowed = requested_offline_pass and requested_online_pass
        if rollout_allowed:
            checks.append(
                {
                    "name": "effective_profile_resolution",
                    "passed": True,
                    "detail": f"using requested prompt profile `{requested_profile_id}`",
                }
            )
            return {
                "status": "active" if not requires_online_gate else "promoted",
                "requested": deepcopy(self._requested_prompt_summary),
                "effective": deepcopy(self._requested_prompt_summary),
                "stable_profile_id": stable_profile_id,
                "allow_blocked_rollout": self._allow_blocked_rollout,
                "checks": checks,
                "effective_prompt_context": deepcopy(self._requested_prompt_context),
            }

        if self._allow_blocked_rollout:
            checks.append(
                {
                    "name": "blocked_rollout_override",
                    "passed": True,
                    "detail": "blocked rollout override enabled; using requested prompt profile",
                }
            )
            return {
                "status": "override_allowed",
                "requested": deepcopy(self._requested_prompt_summary),
                "effective": deepcopy(self._requested_prompt_summary),
                "stable_profile_id": stable_profile_id,
                "allow_blocked_rollout": self._allow_blocked_rollout,
                "checks": checks,
                "effective_prompt_context": deepcopy(self._requested_prompt_context),
            }

        if not requires_online_gate:
            raise RuntimeError(
                f"Stable prompt profile `{requested_profile_id}` failed required rollout gates."
            )

        stable_offline_gate = offline_by_profile.get(stable_profile_id)
        if stable_offline_gate is None or str(stable_offline_gate["status"]) != "pass":
            raise RuntimeError(
                f"Cannot fall back to stable prompt profile `{stable_profile_id}` because its "
                "offline gate is not passing."
            )

        checks.append(
            {
                "name": "blocked_rollout_override",
                "passed": False,
                "detail": "blocked rollout override disabled; fallback to stable profile required",
            }
        )
        checks.append(
            {
                "name": "effective_profile_resolution",
                "passed": False,
                "detail": (
                    f"requested rollout blocked; falling back to stable prompt profile "
                    f"`{stable_profile_id}`"
                ),
            }
        )
        return {
            "status": "blocked",
            "requested": deepcopy(self._requested_prompt_summary),
            "effective": deepcopy(self._stable_prompt_summary),
            "stable_profile_id": stable_profile_id,
            "allow_blocked_rollout": self._allow_blocked_rollout,
            "checks": checks,
            "effective_prompt_context": deepcopy(self._stable_prompt_context),
        }

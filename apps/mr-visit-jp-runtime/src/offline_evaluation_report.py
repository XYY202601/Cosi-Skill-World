from __future__ import annotations

import argparse
import json
from typing import Any

from providers import load_runtime_prompt_context_from_env
from scenarios.asset_loader import get_domain_bundle
from services.evaluation_gate_service import EvaluationGateService


class EmptySessionStore:
    def create(self, session_id: str, payload: dict[str, Any], *, org_id: str | None = None) -> None:
        raise RuntimeError("EmptySessionStore does not support create")

    def upsert(self, session_id: str, payload: dict[str, Any], *, org_id: str | None = None) -> None:
        raise RuntimeError("EmptySessionStore does not support upsert")

    def get(self, session_id: str, *, org_id: str | None = None) -> dict[str, Any] | None:
        return None

    def list_all(self, *, org_id: str | None = None) -> list[dict[str, Any]]:
        return []


def build_offline_profile_deltas(report: dict[str, Any]) -> list[dict[str, Any]]:
    baseline_profile_id = str(report["default_profile_id"])
    offline_gates = [
        item for item in report.get("offline_gates", [])
        if isinstance(item, dict)
    ]
    baseline_gate = next(
        (item for item in offline_gates if str(item.get("profile_id")) == baseline_profile_id),
        None,
    )
    if baseline_gate is None:
        return []

    baseline_contract_versions = (
        baseline_gate.get("contract_versions", {})
        if isinstance(baseline_gate.get("contract_versions"), dict)
        else {}
    )
    baseline_output_requirement_counts = (
        baseline_gate.get("output_requirement_counts", {})
        if isinstance(baseline_gate.get("output_requirement_counts"), dict)
        else {}
    )
    baseline_fixture_pass_rate = float(baseline_gate.get("fixture_pass_rate", 0.0))

    deltas: list[dict[str, Any]] = []
    for gate in offline_gates:
        profile_id = str(gate.get("profile_id"))
        if profile_id == baseline_profile_id:
            continue

        contract_versions = (
            gate.get("contract_versions", {})
            if isinstance(gate.get("contract_versions"), dict)
            else {}
        )
        output_requirement_counts = (
            gate.get("output_requirement_counts", {})
            if isinstance(gate.get("output_requirement_counts"), dict)
            else {}
        )

        roles = sorted(
            set(baseline_contract_versions.keys())
            | set(contract_versions.keys())
            | set(baseline_output_requirement_counts.keys())
            | set(output_requirement_counts.keys())
        )
        contract_version_delta = {
            role: int(contract_versions.get(role, 0)) - int(baseline_contract_versions.get(role, 0))
            for role in roles
            if int(contract_versions.get(role, 0)) - int(baseline_contract_versions.get(role, 0)) != 0
        }
        output_requirement_delta = {
            role: int(output_requirement_counts.get(role, 0)) - int(baseline_output_requirement_counts.get(role, 0))
            for role in roles
            if int(output_requirement_counts.get(role, 0))
            - int(baseline_output_requirement_counts.get(role, 0)) != 0
        }

        deltas.append(
            {
                "baseline_profile_id": baseline_profile_id,
                "profile_id": profile_id,
                "status": str(gate.get("status", "unknown")),
                "fixture_pass_rate_delta": round(
                    float(gate.get("fixture_pass_rate", 0.0)) - baseline_fixture_pass_rate,
                    4,
                ),
                "contract_version_delta": contract_version_delta,
                "output_requirement_delta": output_requirement_delta,
            }
        )

    return deltas


def build_offline_evaluation_report() -> dict[str, Any]:
    requested_prompt_context = load_runtime_prompt_context_from_env()
    service = EvaluationGateService(
        domain_bundle=get_domain_bundle(),
        session_store=EmptySessionStore(),
        requested_prompt_context=requested_prompt_context,
    )
    report = service.build_report()
    return {
        **report,
        "offline_profile_deltas": build_offline_profile_deltas(report),
    }


def render_offline_evaluation_report_text(report: dict[str, Any]) -> str:
    offline_dataset = report["offline_dataset"]
    coverage = offline_dataset["coverage"]
    lines = [
        f"Domain: {report['domain_id']}",
        f"Default profile: {report['default_profile_id']}",
        (
            "Offline dataset: "
            f"{offline_dataset['fixture_count']} fixtures "
            f"(schema v{offline_dataset['fixture_schema_version']})"
        ),
        "Buckets: "
        + ", ".join(
            f"{bucket}={count}"
            for bucket, count in sorted(offline_dataset["fixtures_by_bucket"].items())
        ),
        "Coverage gaps:",
        "  scenarios: "
        + (", ".join(coverage["scenarios"]["missing"]) or "none"),
        "  subskills: "
        + (", ".join(coverage["subskills"]["missing"]) or "none"),
        "  compliance_cases: "
        + (", ".join(coverage["compliance_cases"]["missing"]) or "none"),
        "  finish_reasons: "
        + (", ".join(coverage["finish_reasons"]["missing"]) or "none"),
        "Offline gate deltas:",
    ]
    deltas = report.get("offline_profile_deltas", [])
    if not deltas:
        lines.append("  none")
    else:
        for item in deltas:
            lines.append(
                "  {profile_id}: status={status} fixture_pass_rate_delta={fixture_pass_rate_delta:+.2f}".format(
                    **item
                )
            )
            contract_delta = item.get("contract_version_delta", {})
            if contract_delta:
                lines.append(
                    "    contract_version_delta: "
                    + ", ".join(f"{role}={delta:+d}" for role, delta in sorted(contract_delta.items()))
                )
            output_delta = item.get("output_requirement_delta", {})
            if output_delta:
                lines.append(
                    "    output_requirement_delta: "
                    + ", ".join(f"{role}={delta:+d}" for role, delta in sorted(output_delta.items()))
                )
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run MR visit JP offline evaluation gates and summarize fixture coverage/deltas.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser


def main() -> int:
    args = _build_arg_parser().parse_args()
    report = build_offline_evaluation_report()
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_offline_evaluation_report_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

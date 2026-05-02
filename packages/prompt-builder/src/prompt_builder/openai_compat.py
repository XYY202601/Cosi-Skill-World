from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence


DEFAULT_SYSTEM_PREAMBLE = (
    "You are a structured artifact generator for Japanese MR visit training.",
    "You must return a single strict JSON object and no markdown.",
)

DEFAULT_REQUIRED_OUTPUT_KEYS = (
    "judge_review",
    "coaching_feedback",
    "compliance_flags",
)


@dataclass(frozen=True)
class RenderedPrompt:
    system_prompt: str
    user_payload: dict[str, Any]

    def to_request_body(
        self,
        *,
        model: str,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": json.dumps(self.user_payload, ensure_ascii=False)},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }


def compose_openai_compat_system_prompt(
    *,
    prompt_contracts: dict[str, dict[str, Any]],
    roles: Sequence[str],
    system_preamble: Sequence[str] = DEFAULT_SYSTEM_PREAMBLE,
) -> str:
    sections = [section for section in system_preamble if section]
    for role in roles:
        section = str(prompt_contracts[role]["system_prompt"])
        sections.append(f"[{role}] {section}")
    return "\n\n".join(sections)


def build_openai_compat_user_payload(
    *,
    prompt_contracts: dict[str, dict[str, Any]],
    prompt_context_summary: dict[str, Any],
    turns: list[dict[str, Any]],
    turn_count: int,
    scenario_focus_subskills: list[str],
    subskill_ids: list[str],
    roles: Sequence[str],
    domain: str,
    required_output_keys: Sequence[str] = DEFAULT_REQUIRED_OUTPUT_KEYS,
) -> dict[str, Any]:
    contract_payload: dict[str, Any] = {}
    for role in roles:
        contract = prompt_contracts[role]
        contract_payload[role] = {
            "contract_id": contract.get("contract_id", f"{role}:v{contract['version']}"),
            "version": contract["version"],
            "task_prompt": contract["task_prompt"],
            "output_requirements": contract["output_requirements"],
        }
    return {
        "domain": domain,
        "prompting": prompt_context_summary,
        "turn_count": turn_count,
        "scenario_focus_subskills": scenario_focus_subskills,
        "subskill_ids": subskill_ids,
        "turns": turns,
        "contracts": contract_payload,
        "required_output_keys": list(required_output_keys),
    }


def render_openai_compat_prompt(
    *,
    prompt_contracts: dict[str, dict[str, Any]],
    prompt_context_summary: dict[str, Any],
    turns: list[dict[str, Any]],
    turn_count: int,
    scenario_focus_subskills: list[str],
    subskill_ids: list[str],
    roles: Sequence[str],
    domain: str,
    required_output_keys: Sequence[str] = DEFAULT_REQUIRED_OUTPUT_KEYS,
    system_preamble: Sequence[str] = DEFAULT_SYSTEM_PREAMBLE,
) -> RenderedPrompt:
    return RenderedPrompt(
        system_prompt=compose_openai_compat_system_prompt(
            prompt_contracts=prompt_contracts,
            roles=roles,
            system_preamble=system_preamble,
        ),
        user_payload=build_openai_compat_user_payload(
            prompt_contracts=prompt_contracts,
            prompt_context_summary=prompt_context_summary,
            turns=turns,
            turn_count=turn_count,
            scenario_focus_subskills=scenario_focus_subskills,
            subskill_ids=subskill_ids,
            roles=roles,
            domain=domain,
            required_output_keys=required_output_keys,
        ),
    )

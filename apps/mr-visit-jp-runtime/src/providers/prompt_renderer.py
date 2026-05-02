from __future__ import annotations

from typing import Any

from prompt_builder.openai_compat import (
    RenderedPrompt,
    build_openai_compat_user_payload as _build_openai_compat_user_payload,
    compose_openai_compat_system_prompt as _compose_openai_compat_system_prompt,
    render_openai_compat_prompt as _render_openai_compat_prompt,
)

from providers.prompt_assets import PROMPT_ROLES, summarize_prompt_context


def compose_openai_compat_system_prompt(prompt_contracts: dict[str, dict[str, Any]]) -> str:
    return _compose_openai_compat_system_prompt(
        prompt_contracts=prompt_contracts,
        roles=PROMPT_ROLES,
    )


def build_openai_compat_user_payload(
    *,
    prompt_contracts: dict[str, dict[str, Any]],
    prompt_context: dict[str, Any] | None,
    turns: list[dict[str, Any]],
    turn_count: int,
    scenario_focus_subskills: list[str],
    subskill_ids: list[str],
) -> dict[str, Any]:
    return _build_openai_compat_user_payload(
        prompt_contracts=prompt_contracts,
        prompt_context_summary=summarize_prompt_context(prompt_context),
        turns=turns,
        turn_count=turn_count,
        scenario_focus_subskills=scenario_focus_subskills,
        subskill_ids=subskill_ids,
        roles=PROMPT_ROLES,
        domain="mr_visit_jp",
    )


def render_openai_compat_prompt(
    *,
    prompt_contracts: dict[str, dict[str, Any]],
    prompt_context: dict[str, Any] | None,
    turns: list[dict[str, Any]],
    turn_count: int,
    scenario_focus_subskills: list[str],
    subskill_ids: list[str],
) -> RenderedPrompt:
    return _render_openai_compat_prompt(
        prompt_contracts=prompt_contracts,
        prompt_context_summary=summarize_prompt_context(prompt_context),
        turns=turns,
        turn_count=turn_count,
        scenario_focus_subskills=scenario_focus_subskills,
        subskill_ids=subskill_ids,
        roles=PROMPT_ROLES,
        domain="mr_visit_jp",
    )

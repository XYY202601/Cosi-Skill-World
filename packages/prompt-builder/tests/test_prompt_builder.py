from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt_builder import (
    PromptAssetError,
    PromptAssetManager,
    render_openai_compat_prompt,
    summarize_prompt_context,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_ROOT = REPO_ROOT / "domains" / "mr_visit_jp" / "prompts"
SNAPSHOT_DIR = REPO_ROOT / "tests" / "fixtures" / "prompt_snapshots"
PROMPT_PROVIDER = "openai_compat"
PROMPT_ROLES = ("judge", "coach", "compliance")


def _write_prompt_assets(
    root: Path,
    *,
    coach_version: int = 1,
    registry_text: str | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for role, system_label in (
        ("judge", "Judge"),
        ("coach", "Coach"),
        ("compliance", "Compliance"),
    ):
        role_dir = root / role
        role_dir.mkdir(parents=True, exist_ok=True)
        version = coach_version if role == "coach" else 1
        (role_dir / "openai_compat.yaml").write_text(
            (
                f"version: {version}\n"
                f"role: {role}\n"
                "system_prompt: |\n"
                f"  {system_label} system prompt.\n"
                "task_prompt: |\n"
                f"  {system_label} task prompt.\n"
                "output_requirements:\n"
                f"  - {system_label} requirement.\n"
            ),
            encoding="utf-8",
        )

    registry_payload = registry_text or (
        "default_profile: alpha_baseline_v1\n"
        "profiles:\n"
        "  alpha_baseline_v1:\n"
        "    description: Baseline profile.\n"
        "    experiment_flags: []\n"
        "    roles: {}\n"
    )
    (root / "openai_compat_profiles.yaml").write_text(registry_payload, encoding="utf-8")
    return root


def _load_snapshot(name: str) -> dict[str, object]:
    return json.loads((SNAPSHOT_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _render_snapshot(profile_id: str) -> dict[str, object]:
    manager = PromptAssetManager(
        root=PROMPTS_ROOT,
        provider=PROMPT_PROVIDER,
        roles=PROMPT_ROLES,
    )
    prompt_context = manager.load_bundle().resolve_prompt_context(
        profile_id=profile_id,
        experiment_id="prompt-snapshot-exp",
        extra_flags=["snapshot_test"],
    )
    rendered = render_openai_compat_prompt(
        prompt_contracts=prompt_context["contracts"],
        prompt_context_summary=summarize_prompt_context(prompt_context, roles=PROMPT_ROLES),
        turns=[
            {
                "turn_index": 1,
                "user_message": "本日は3分だけ、先生の患者像に合う話題を一つだけ共有してもよいでしょうか。",
                "doctor_reply": "短めでお願いします。どの患者さん向けですか。",
            },
            {
                "turn_index": 2,
                "user_message": "高齢で再発リスクを気にされる患者さんに絞って、主要データを一つだけ確認したいです。",
                "doctor_reply": "その根拠と安全性の見方を簡潔に教えてください。",
            },
        ],
        turn_count=2,
        scenario_focus_subskills=["opening", "need_discovery", "scientific_delivery"],
        subskill_ids=[
            "opening",
            "profiling",
            "scientific_delivery",
            "need_discovery",
            "objection_handling",
            "closing_followup",
        ],
        roles=PROMPT_ROLES,
        domain="mr_visit_jp",
    )
    return {
        "system_prompt": rendered.system_prompt,
        "user_payload": rendered.user_payload,
    }


def test_prompt_asset_manager_invalidates_cache_when_files_change(tmp_path: Path) -> None:
    root = _write_prompt_assets(tmp_path / "prompts")
    manager = PromptAssetManager(
        root=root,
        provider=PROMPT_PROVIDER,
        roles=PROMPT_ROLES,
    )

    first_bundle = manager.load_bundle()
    assert manager.load_bundle() is first_bundle
    assert first_bundle.resolve_contracts()["coach"]["version"] == 1

    _write_prompt_assets(root, coach_version=2)

    second_bundle = manager.load_bundle()
    assert second_bundle is not first_bundle
    assert second_bundle.resolve_contracts()["coach"]["version"] == 2


def test_prompt_asset_manager_requires_version_bump_for_content_override(tmp_path: Path) -> None:
    root = _write_prompt_assets(
        tmp_path / "prompts",
        registry_text=(
            "default_profile: alpha_baseline_v1\n"
            "profiles:\n"
            "  alpha_baseline_v1:\n"
            "    description: Baseline profile.\n"
            "    experiment_flags: []\n"
            "    roles: {}\n"
            "  invalid_profile:\n"
            "    description: Invalid content change without version bump.\n"
            "    experiment_flags: []\n"
            "    roles:\n"
            "      coach:\n"
            "        task_prompt_suffix: |\n"
            "          Keep the next action under 10 words.\n"
        ),
    )
    manager = PromptAssetManager(
        root=root,
        provider=PROMPT_PROVIDER,
        roles=PROMPT_ROLES,
    )

    with pytest.raises(
        PromptAssetError,
        match="must set `version` when modifying prompt content",
    ):
        manager.load_bundle()


@pytest.mark.parametrize(
    ("profile_id", "snapshot_name"),
    [
        ("alpha_baseline_v1", "alpha_baseline_v1_rendered_prompt"),
        ("alpha_coach_concise_v1", "alpha_coach_concise_v1_rendered_prompt"),
    ],
)
def test_rendered_prompt_matches_snapshot(profile_id: str, snapshot_name: str) -> None:
    assert _render_snapshot(profile_id) == _load_snapshot(snapshot_name)

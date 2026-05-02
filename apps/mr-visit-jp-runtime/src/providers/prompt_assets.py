from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from prompt_builder import (
    PromptAssetBundle,
    PromptAssetError,
    parse_env_flag_list,
    summarize_prompt_context as _summarize_prompt_context,
)
from prompt_builder.assets import PromptAssetManager as SharedPromptAssetManager


REPO_ROOT = Path(__file__).resolve().parents[4]
PROMPTS_ROOT = REPO_ROOT / "domains" / "mr_visit_jp" / "prompts"
PROMPT_PROVIDER = "openai_compat"
PROMPT_ROLES = ("judge", "coach", "compliance")


class PromptAssetManager(SharedPromptAssetManager):
    def __init__(self, root: Path = PROMPTS_ROOT):
        super().__init__(root=root, provider=PROMPT_PROVIDER, roles=PROMPT_ROLES)


_DEFAULT_PROMPT_ASSET_MANAGER = PromptAssetManager()


def get_prompt_asset_manager() -> PromptAssetManager:
    return _DEFAULT_PROMPT_ASSET_MANAGER


def clear_prompt_asset_cache() -> None:
    get_prompt_asset_manager().invalidate_cache()


def load_prompt_asset_bundle() -> PromptAssetBundle:
    return get_prompt_asset_manager().load_bundle()


def load_openai_compat_prompt_contracts(
    *,
    profile_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    return load_prompt_asset_bundle().resolve_contracts(profile_id=profile_id)


def load_runtime_prompt_context(
    *,
    profile_id: str | None = None,
    experiment_id: str | None = None,
    extra_flags: list[str] | None = None,
) -> dict[str, Any]:
    return load_prompt_asset_bundle().resolve_prompt_context(
        profile_id=profile_id,
        experiment_id=experiment_id,
        extra_flags=extra_flags,
    )


def load_runtime_prompt_context_from_env() -> dict[str, Any]:
    selected_profile = os.getenv("MR_RUNTIME_PROMPT_PROFILE", "").strip() or None
    experiment_id = os.getenv("MR_RUNTIME_EXPERIMENT_ID", "").strip() or None
    extra_flags = parse_env_flag_list(os.getenv("MR_RUNTIME_EXPERIMENT_FLAGS"))
    return load_runtime_prompt_context(
        profile_id=selected_profile,
        experiment_id=experiment_id,
        extra_flags=extra_flags,
    )


def list_prompt_profile_ids() -> list[str]:
    return load_prompt_asset_bundle().list_profile_ids()


def summarize_prompt_context(prompt_context: dict[str, Any] | None) -> dict[str, Any]:
    return _summarize_prompt_context(prompt_context, roles=PROMPT_ROLES)

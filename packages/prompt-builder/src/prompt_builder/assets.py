from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml


class PromptAssetError(RuntimeError):
    """Raised when prompt assets fail validation or lookup."""


def _read_yaml_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = yaml.safe_load(f)
    except Exception as exc:
        raise PromptAssetError(f"failed_to_read_prompt_asset `{path}`: {exc}") from exc
    if not isinstance(payload, dict):
        raise PromptAssetError(f"prompt asset `{path}` must be a YAML object")
    return payload


def _optional_non_empty_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PromptAssetError(f"expected string value, got {value!r}")
    normalized = value.strip()
    return normalized or None


def _parse_string_list(
    *,
    value: Any,
    label: str,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise PromptAssetError(f"{label} must be a list of strings")
    output: list[str] = []
    for item in value:
        normalized = _optional_non_empty_string(item)
        if normalized is None:
            raise PromptAssetError(f"{label} contains invalid string entry: {item!r}")
        output.append(normalized)
    return tuple(output)


def dedupe_preserve_order(items: Sequence[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def parse_env_flag_list(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return []
    return dedupe_preserve_order([item.strip() for item in raw_value.split(",") if item.strip()])


def summarize_prompt_context(
    prompt_context: dict[str, Any] | None,
    *,
    roles: Sequence[str],
) -> dict[str, Any]:
    valid_roles = set(roles)
    if not isinstance(prompt_context, dict):
        return {
            "profile_id": "unknown",
            "experiment_id": None,
            "flags": [],
            "contracts": {},
        }

    raw_contracts = prompt_context.get("contracts", {})
    contracts_summary: dict[str, dict[str, Any]] = {}
    if isinstance(raw_contracts, dict):
        for role, payload in raw_contracts.items():
            if role not in valid_roles or not isinstance(payload, dict):
                continue
            contract_id = _optional_non_empty_string(payload.get("contract_id"))
            version = payload.get("version")
            if not isinstance(version, int):
                continue
            contracts_summary[role] = {
                "contract_id": contract_id or f"{role}:v{version}",
                "version": version,
            }

    flags: list[str] = []
    raw_flags = prompt_context.get("flags")
    if isinstance(raw_flags, list):
        for item in raw_flags:
            normalized = _optional_non_empty_string(item)
            if normalized is not None:
                flags.append(normalized)

    profile_id = _optional_non_empty_string(prompt_context.get("profile_id")) or "unknown"
    experiment_id = _optional_non_empty_string(prompt_context.get("experiment_id"))
    return {
        "profile_id": profile_id,
        "experiment_id": experiment_id,
        "flags": flags,
        "contracts": contracts_summary,
    }


def _parse_contract_requirements(
    *,
    payload: dict[str, Any],
    path: Path,
) -> tuple[str, ...]:
    requirements_raw = payload.get("output_requirements")
    if not isinstance(requirements_raw, list) or not requirements_raw:
        raise PromptAssetError(f"prompt contract `{path}` must define non-empty `output_requirements`")
    requirements: list[str] = []
    for item in requirements_raw:
        if not isinstance(item, str) or not item.strip():
            raise PromptAssetError(
                f"prompt contract `{path}` has invalid `output_requirements` entry: {item!r}"
            )
        requirements.append(item.strip())
    return tuple(requirements)


@dataclass(frozen=True)
class PromptContractAsset:
    role: str
    version: int
    system_prompt: str
    task_prompt: str
    output_requirements: tuple[str, ...]
    source_path: Path

    def to_payload(self, *, profile_id: str) -> dict[str, Any]:
        return {
            "contract_id": f"{profile_id}:{self.role}:v{self.version}",
            "version": self.version,
            "role": self.role,
            "system_prompt": self.system_prompt,
            "task_prompt": self.task_prompt,
            "output_requirements": list(self.output_requirements),
        }


@dataclass(frozen=True)
class PromptProfileOverride:
    version: int | None
    system_prompt_suffix: str | None
    task_prompt_suffix: str | None
    output_requirements_append: tuple[str, ...]

    def changes_contract_content(self) -> bool:
        return any(
            (
                self.system_prompt_suffix,
                self.task_prompt_suffix,
                self.output_requirements_append,
            )
        )


@dataclass(frozen=True)
class PromptProfileAsset:
    profile_id: str
    description: str
    experiment_flags: tuple[str, ...]
    role_overrides: dict[str, PromptProfileOverride]


@dataclass(frozen=True)
class PromptAssetBundle:
    root: Path
    provider: str
    roles: tuple[str, ...]
    default_profile_id: str
    base_contracts: dict[str, PromptContractAsset]
    profiles: dict[str, PromptProfileAsset]
    asset_fingerprint: str

    def list_profile_ids(self) -> list[str]:
        return sorted(self.profiles.keys())

    def resolve_profile(self, profile_id: str | None = None) -> PromptProfileAsset:
        selected_profile = profile_id or self.default_profile_id
        profile = self.profiles.get(selected_profile)
        if profile is None:
            raise PromptAssetError(f"Unknown prompt profile `{selected_profile}`")
        return profile

    def resolve_contracts(self, profile_id: str | None = None) -> dict[str, dict[str, Any]]:
        profile = self.resolve_profile(profile_id)
        contracts: dict[str, dict[str, Any]] = {}
        for role in self.roles:
            base_contract = self.base_contracts[role]
            override = profile.role_overrides.get(role)
            effective_contract = _apply_prompt_profile_override(
                base_contract=base_contract,
                role_override=override,
            )
            contracts[role] = effective_contract.to_payload(profile_id=profile.profile_id)
        return contracts

    def resolve_prompt_context(
        self,
        *,
        profile_id: str | None = None,
        experiment_id: str | None = None,
        extra_flags: list[str] | None = None,
    ) -> dict[str, Any]:
        profile = self.resolve_profile(profile_id)
        flags = dedupe_preserve_order([*profile.experiment_flags, *(extra_flags or [])])
        return {
            "profile_id": profile.profile_id,
            "experiment_id": experiment_id,
            "flags": flags,
            "description": profile.description,
            "contracts": self.resolve_contracts(profile.profile_id),
        }

    def describe(self) -> dict[str, Any]:
        versions: dict[str, dict[str, int]] = {}
        for profile_id in self.list_profile_ids():
            contracts = self.resolve_contracts(profile_id)
            versions[profile_id] = {
                role: int(contracts[role]["version"])
                for role in self.roles
            }
        return {
            "default_profile_id": self.default_profile_id,
            "profile_count": len(self.profiles),
            "profiles": versions,
            "asset_fingerprint": self.asset_fingerprint,
        }


def _contract_path(root: Path, provider: str, role: str) -> Path:
    return root / role / f"{provider}.yaml"


def _load_prompt_contract(*, root: Path, provider: str, role: str) -> PromptContractAsset:
    path = _contract_path(root, provider, role)
    payload = _read_yaml_object(path)
    payload_role = payload.get("role")
    if payload_role != role:
        raise PromptAssetError(
            f"prompt contract `{path}` role mismatch: expected `{role}`, got `{payload_role}`"
        )

    version = payload.get("version")
    if not isinstance(version, int) or version <= 0:
        raise PromptAssetError(f"prompt contract `{path}` must define positive integer `version`")

    system_prompt = payload.get("system_prompt")
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise PromptAssetError(f"prompt contract `{path}` must define non-empty `system_prompt`")

    task_prompt = payload.get("task_prompt")
    if not isinstance(task_prompt, str) or not task_prompt.strip():
        raise PromptAssetError(f"prompt contract `{path}` must define non-empty `task_prompt`")

    output_requirements = _parse_contract_requirements(payload=payload, path=path)

    return PromptContractAsset(
        role=role,
        version=version,
        system_prompt=system_prompt.strip(),
        task_prompt=task_prompt.strip(),
        output_requirements=output_requirements,
        source_path=path,
    )


def _parse_prompt_profile_override(
    *,
    profile_id: str,
    role: str,
    raw_override: dict[str, Any],
) -> PromptProfileOverride:
    override_version = raw_override.get("version")
    if override_version is not None:
        if not isinstance(override_version, int) or override_version <= 0:
            raise PromptAssetError(
                f"prompt profile `{profile_id}` role `{role}` must use positive integer `version`"
            )

    return PromptProfileOverride(
        version=override_version,
        system_prompt_suffix=_optional_non_empty_string(raw_override.get("system_prompt_suffix")),
        task_prompt_suffix=_optional_non_empty_string(raw_override.get("task_prompt_suffix")),
        output_requirements_append=_parse_string_list(
            value=raw_override.get("output_requirements_append"),
            label=f"prompt profile `{profile_id}` role `{role}` output_requirements_append",
        ),
    )


def _validate_prompt_profile_override(
    *,
    profile_id: str,
    role: str,
    base_contract: PromptContractAsset,
    override: PromptProfileOverride,
) -> None:
    changes_contract = override.changes_contract_content()
    if changes_contract:
        if override.version is None:
            raise PromptAssetError(
                f"prompt profile `{profile_id}` role `{role}` must set `version` when modifying "
                "prompt content"
            )
        if override.version <= base_contract.version:
            raise PromptAssetError(
                f"prompt profile `{profile_id}` role `{role}` version {override.version} must be "
                f"greater than base version {base_contract.version}"
            )
        return

    if override.version is not None and override.version != base_contract.version:
        raise PromptAssetError(
            f"prompt profile `{profile_id}` role `{role}` cannot change `version` without "
            "modifying prompt content"
        )


def _load_prompt_profiles(
    *,
    root: Path,
    provider: str,
    roles: tuple[str, ...],
    base_contracts: dict[str, PromptContractAsset],
) -> tuple[str, dict[str, PromptProfileAsset]]:
    registry_path = root / f"{provider}_profiles.yaml"
    payload = _read_yaml_object(registry_path)

    default_profile = _optional_non_empty_string(payload.get("default_profile"))
    if default_profile is None:
        raise PromptAssetError(f"prompt profile registry `{registry_path}` must define `default_profile`")

    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise PromptAssetError(
            f"prompt profile registry `{registry_path}` must define non-empty `profiles`"
        )

    valid_roles = set(roles)
    profiles: dict[str, PromptProfileAsset] = {}
    for raw_profile_id, raw_profile in raw_profiles.items():
        profile_id = _optional_non_empty_string(raw_profile_id)
        if profile_id is None:
            raise PromptAssetError(
                f"prompt profile registry `{registry_path}` has invalid profile id"
            )
        if not isinstance(raw_profile, dict):
            raise PromptAssetError(f"prompt profile `{profile_id}` must be an object")

        roles_payload = raw_profile.get("roles", {})
        if not isinstance(roles_payload, dict):
            raise PromptAssetError(f"prompt profile `{profile_id}` roles must be an object")

        role_overrides: dict[str, PromptProfileOverride] = {}
        for role, raw_override in roles_payload.items():
            if role not in valid_roles:
                raise PromptAssetError(f"prompt profile `{profile_id}` references unknown role `{role}`")
            if not isinstance(raw_override, dict):
                raise PromptAssetError(
                    f"prompt profile `{profile_id}` role override `{role}` must be an object"
                )
            override = _parse_prompt_profile_override(
                profile_id=profile_id,
                role=role,
                raw_override=raw_override,
            )
            _validate_prompt_profile_override(
                profile_id=profile_id,
                role=role,
                base_contract=base_contracts[role],
                override=override,
            )
            role_overrides[role] = override

        profiles[profile_id] = PromptProfileAsset(
            profile_id=profile_id,
            description=_optional_non_empty_string(raw_profile.get("description")) or "",
            experiment_flags=_parse_string_list(
                value=raw_profile.get("experiment_flags"),
                label=f"prompt profile `{profile_id}` experiment_flags",
            ),
            role_overrides=role_overrides,
        )

    if default_profile not in profiles:
        raise PromptAssetError(
            f"prompt profile registry `{registry_path}` default profile `{default_profile}` is not defined"
        )

    return default_profile, profiles


def _apply_prompt_profile_override(
    *,
    base_contract: PromptContractAsset,
    role_override: PromptProfileOverride | None,
) -> PromptContractAsset:
    if role_override is None:
        return base_contract

    system_prompt = base_contract.system_prompt
    if role_override.system_prompt_suffix is not None:
        system_prompt = f"{system_prompt}\n{role_override.system_prompt_suffix}"

    task_prompt = base_contract.task_prompt
    if role_override.task_prompt_suffix is not None:
        task_prompt = f"{task_prompt}\n{role_override.task_prompt_suffix}"

    requirements = tuple(
        dedupe_preserve_order(
            [
                *base_contract.output_requirements,
                *role_override.output_requirements_append,
            ]
        )
    )

    version = role_override.version or base_contract.version
    return PromptContractAsset(
        role=base_contract.role,
        version=version,
        system_prompt=system_prompt,
        task_prompt=task_prompt,
        output_requirements=requirements,
        source_path=base_contract.source_path,
    )


class PromptAssetManager:
    def __init__(self, *, root: Path, provider: str, roles: Sequence[str]):
        normalized_roles = tuple(roles)
        if not normalized_roles:
            raise PromptAssetError("prompt asset manager requires at least one role")
        self.root = root
        self.provider = provider
        self.roles = normalized_roles
        self._cached_bundle: PromptAssetBundle | None = None
        self._cached_signature: str | None = None

    def _watched_paths(self) -> list[Path]:
        return [
            self.root / f"{self.provider}_profiles.yaml",
            *[_contract_path(self.root, self.provider, role) for role in self.roles],
        ]

    def _compute_signature(self) -> str:
        hasher = hashlib.sha256()
        for path in self._watched_paths():
            hasher.update(str(path.relative_to(self.root)).encode("utf-8"))
            if path.is_file():
                hasher.update(path.read_bytes())
            else:
                hasher.update(b"<missing>")
        return hasher.hexdigest()

    def invalidate_cache(self) -> None:
        self._cached_bundle = None
        self._cached_signature = None

    def load_bundle(self) -> PromptAssetBundle:
        signature = self._compute_signature()
        if self._cached_bundle is not None and signature == self._cached_signature:
            return self._cached_bundle

        base_contracts = {
            role: _load_prompt_contract(root=self.root, provider=self.provider, role=role)
            for role in self.roles
        }
        default_profile_id, profiles = _load_prompt_profiles(
            root=self.root,
            provider=self.provider,
            roles=self.roles,
            base_contracts=base_contracts,
        )
        bundle = PromptAssetBundle(
            root=self.root,
            provider=self.provider,
            roles=self.roles,
            default_profile_id=default_profile_id,
            base_contracts=base_contracts,
            profiles=profiles,
            asset_fingerprint=signature,
        )
        self._cached_bundle = bundle
        self._cached_signature = signature
        return bundle

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


PATH_PARAM_PATTERN = re.compile(r"{([a-z][a-z0-9_]*)}")


class SkillRegistryError(RuntimeError):
    """Raised when skill manifests or registry state are invalid."""


@dataclass(frozen=True)
class SkillRuntimeSpec:
    app: str
    base_path: str
    health_path: str
    base_url_env: str


@dataclass(frozen=True)
class SkillCapabilitySpec:
    id: str
    name: str
    description: str
    action_ids: tuple[str, ...]


@dataclass(frozen=True)
class SkillActionSpec:
    id: str
    capability_id: str
    method: str
    path: str
    description: str
    expose: tuple[str, ...]
    path_params: tuple[str, ...]

    def build_runtime_path(
        self,
        *,
        base_path: str,
        path_values: dict[str, str] | None = None,
    ) -> str:
        path_values = path_values or {}
        resolved_path = self.path
        for param_name in self.path_params:
            if param_name not in path_values:
                raise SkillRegistryError(
                    f"Action `{self.id}` missing path param `{param_name}`"
                )
            resolved_path = resolved_path.replace(
                "{" + param_name + "}",
                str(path_values[param_name]),
            )

        unresolved = PATH_PARAM_PATTERN.findall(resolved_path)
        if unresolved:
            raise SkillRegistryError(
                f"Action `{self.id}` still has unresolved path params: {sorted(unresolved)}"
            )
        return f"{base_path.rstrip('/')}{resolved_path}"

    def is_exposed_at(self, surface: str) -> bool:
        return surface in self.expose


@dataclass(frozen=True)
class MarketplaceMetadata:
    """Optional marketplace display metadata for a skill."""

    title: str = ""
    summary: str = ""
    provider: str = ""
    locales: tuple[str, ...] = ()
    modality: str = ""
    maturity: str = ""
    min_runtime_version: str = ""
    data_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.title:
            d["title"] = self.title
        if self.summary:
            d["summary"] = self.summary
        if self.provider:
            d["provider"] = self.provider
        if self.locales:
            d["locales"] = list(self.locales)
        if self.modality:
            d["modality"] = self.modality
        if self.maturity:
            d["maturity"] = self.maturity
        if self.min_runtime_version or self.data_notes:
            compat: dict[str, Any] = {}
            if self.min_runtime_version:
                compat["min_runtime_version"] = self.min_runtime_version
            if compat:
                d["compatibility"] = compat
            privacy: dict[str, Any] = {}
            if self.data_notes:
                privacy["data_notes"] = self.data_notes
            if privacy:
                d["privacy"] = privacy
        return d


@dataclass(frozen=True)
class SkillManifest:
    id: str
    version: str
    name: str
    registration_enabled: bool
    default_for_unscoped_routes: bool
    runtime: SkillRuntimeSpec
    capabilities: tuple[SkillCapabilitySpec, ...]
    actions: tuple[SkillActionSpec, ...]
    subskills: tuple[str, ...]
    ui: dict[str, Any]
    source_path: Path
    marketplace: MarketplaceMetadata = field(default_factory=MarketplaceMetadata)

    def action(self, action_id: str) -> SkillActionSpec:
        for action in self.actions:
            if action.id == action_id:
                return action
        raise SkillRegistryError(f"Unknown action `{action_id}` for skill `{self.id}`")

    def capability(self, capability_id: str) -> SkillCapabilitySpec:
        for capability in self.capabilities:
            if capability.id == capability_id:
                return capability
        raise SkillRegistryError(
            f"Unknown capability `{capability_id}` for skill `{self.id}`"
        )

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "registration_enabled": self.registration_enabled,
            "default_for_unscoped_routes": self.default_for_unscoped_routes,
            "runtime": {
                "app": self.runtime.app,
                "base_path": self.runtime.base_path,
                "health_path": self.runtime.health_path,
                "base_url_env": self.runtime.base_url_env,
            },
            "ui": dict(self.ui),
            "marketplace": self.marketplace.to_dict() if self.marketplace.title else None,
            "capabilities": [
                {
                    "id": capability.id,
                    "name": capability.name,
                    "description": capability.description,
                    "actions": list(capability.action_ids),
                }
                for capability in self.capabilities
            ],
            "actions": [
                {
                    "id": action.id,
                    "capability": action.capability_id,
                    "method": action.method,
                    "path": action.path,
                    "expose": list(action.expose),
                    "path_params": list(action.path_params),
                    "description": action.description,
                }
                for action in self.actions
            ],
            "subskills": list(self.subskills),
        }


class SkillRegistry:
    def __init__(self, skills: list[SkillManifest]) -> None:
        if not skills:
            raise SkillRegistryError("Skill registry requires at least one manifest")

        skill_ids = [skill.id for skill in skills]
        if len(skill_ids) != len(set(skill_ids)):
            raise SkillRegistryError(f"Duplicate skill ids found: {skill_ids}")

        self._skills = {skill.id: skill for skill in skills}
        defaults = [skill.id for skill in skills if skill.default_for_unscoped_routes]
        if len(defaults) > 1:
            raise SkillRegistryError(
                "Only one skill may set default_for_unscoped_routes=true"
            )
        self._default_skill_id = defaults[0] if defaults else None

    def list_skill_ids(self) -> list[str]:
        return sorted(self._skills.keys())

    def list_summaries(self) -> list[dict[str, Any]]:
        return [self._skills[skill_id].to_summary() for skill_id in self.list_skill_ids()]

    def get(self, skill_id: str) -> SkillManifest | None:
        return self._skills.get(skill_id)

    def require(self, skill_id: str) -> SkillManifest:
        skill = self.get(skill_id)
        if skill is None:
            raise SkillRegistryError(f"Unknown skill_id: {skill_id}")
        return skill

    def default_skill(self) -> SkillManifest:
        if not self._default_skill_id:
            raise SkillRegistryError("No default skill configured for unscoped routes")
        return self._skills[self._default_skill_id]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _schemas_dir() -> Path:
    return _repo_root() / "packages" / "shared-schemas" / "schemas"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise SkillRegistryError(f"Expected JSON object in {path}")
    return payload


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    if not isinstance(payload, dict):
        raise SkillRegistryError(f"Expected YAML object in {path}")
    return payload


def _manifest_registration_enabled(payload: dict[str, Any]) -> bool:
    registration = payload.get("registration")
    if not isinstance(registration, dict):
        return True
    return registration.get("enabled") is not False


def _validate_manifest_schema(payload: dict[str, Any], source_path: Path) -> None:
    schema = _read_json(_schemas_dir() / "skill_manifest.schema.json")
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.path) or "<root>"
        raise SkillRegistryError(
            f"Schema validation failed for {source_path} at {path}: {first.message}"
        )


def _normalize_path_params(action_id: str, path: str, raw_params: list[str]) -> tuple[str, ...]:
    placeholder_params = tuple(PATH_PARAM_PATTERN.findall(path))
    declared_params = tuple(raw_params)
    if declared_params != placeholder_params:
        raise SkillRegistryError(
            f"Action `{action_id}` path params must match placeholders in `{path}`: "
            f"declared={declared_params} placeholders={placeholder_params}"
        )
    return declared_params


def load_skill_manifest(source_path: Path) -> SkillManifest:
    payload = _read_yaml(source_path)
    _validate_manifest_schema(payload, source_path)

    runtime_payload = payload["runtime"]
    runtime = SkillRuntimeSpec(
        app=str(runtime_payload["app"]),
        base_path=str(runtime_payload["base_path"]),
        health_path=str(runtime_payload["health_path"]),
        base_url_env=str(runtime_payload["base_url_env"]),
    )

    capabilities = tuple(
        SkillCapabilitySpec(
            id=str(item["id"]),
            name=str(item["name"]),
            description=str(item["description"]),
            action_ids=tuple(str(action_id) for action_id in item["actions"]),
        )
        for item in payload["capabilities"]
    )

    actions = tuple(
        SkillActionSpec(
            id=str(item["id"]),
            capability_id=str(item["capability"]),
            method=str(item["method"]),
            path=str(item["path"]),
            description=str(item["description"]),
            expose=tuple(str(surface) for surface in item["expose"]),
            path_params=_normalize_path_params(
                str(item["id"]),
                str(item["path"]),
                [str(path_param) for path_param in item.get("path_params", [])],
            ),
        )
        for item in payload["actions"]
    )

    capability_ids = {capability.id for capability in capabilities}
    action_ids = {action.id for action in actions}

    if len(capability_ids) != len(capabilities):
        raise SkillRegistryError(
            f"Manifest `{source_path}` contains duplicate capability ids"
        )
    if len(action_ids) != len(actions):
        raise SkillRegistryError(
            f"Manifest `{source_path}` contains duplicate action ids"
        )

    for action in actions:
        if action.capability_id not in capability_ids:
            raise SkillRegistryError(
                f"Action `{action.id}` references unknown capability `{action.capability_id}`"
            )

    for capability in capabilities:
        missing_actions = sorted(set(capability.action_ids) - action_ids)
        if missing_actions:
            raise SkillRegistryError(
                f"Capability `{capability.id}` references unknown actions: {missing_actions}"
            )

    marketplace_raw = payload.get("marketplace", {})
    if isinstance(marketplace_raw, dict):
        compatibility = marketplace_raw.get("compatibility", {}) or {}
        privacy = marketplace_raw.get("privacy", {}) or {}
        marketplace = MarketplaceMetadata(
            title=str(marketplace_raw.get("title", "")),
            summary=str(marketplace_raw.get("summary", "")),
            provider=str(marketplace_raw.get("provider", "")),
            locales=tuple(str(loc) for loc in marketplace_raw.get("locales", [])),
            modality=str(marketplace_raw.get("modality", "")),
            maturity=str(marketplace_raw.get("maturity", "")),
            min_runtime_version=str(compatibility.get("min_runtime_version", "")),
            data_notes=str(privacy.get("data_notes", "")),
        )
    else:
        marketplace = MarketplaceMetadata()

    return SkillManifest(
        id=str(payload["id"]),
        version=str(payload["version"]),
        name=str(payload["name"]),
        registration_enabled=_manifest_registration_enabled(payload),
        default_for_unscoped_routes=bool(
            payload["routing"]["default_for_unscoped_routes"]
        ),
        runtime=runtime,
        capabilities=capabilities,
        actions=actions,
        subskills=tuple(str(subskill_id) for subskill_id in payload["subskills"]),
        ui=dict(payload.get("ui", {})),
        marketplace=marketplace,
        source_path=source_path,
    )


def _default_manifest_paths() -> list[Path]:
    manifests = sorted((_repo_root() / "domains").glob("*/manifests/skill.yaml"))
    enabled_paths: list[Path] = []
    for path in manifests:
        payload = _read_yaml(path)
        if _manifest_registration_enabled(payload):
            enabled_paths.append(path)
    return enabled_paths


def load_skill_registry(manifest_paths: list[Path] | None = None) -> SkillRegistry:
    paths = manifest_paths or _default_manifest_paths()
    manifests = [load_skill_manifest(path) for path in paths]
    return SkillRegistry(manifests)


@lru_cache(maxsize=1)
def get_skill_registry() -> SkillRegistry:
    return load_skill_registry()


def resolve_runtime_api_base(runtime: SkillRuntimeSpec) -> str:
    specific = os.getenv(runtime.base_url_env)
    if specific:
        return specific.rstrip("/")

    generic = os.getenv("RUNTIME_API_BASE")
    if generic:
        return generic.rstrip("/")

    if runtime.base_url_env == "MR_VISIT_JP_RUNTIME_BASE":
        return "http://127.0.0.1:8100"

    raise SkillRegistryError(
        f"Missing runtime base URL for `{runtime.app}`. Set {runtime.base_url_env}."
    )

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


class DomainAssetError(RuntimeError):
    """Raised when domain assets fail schema or consistency checks."""


@dataclass(frozen=True)
class PlaybookRecord:
    learning_objective: str
    target_subskills: list[str]
    expected_flow: list[str]
    key_discovery_questions: list[str] = field(default_factory=list)
    acceptable_evidence_moves: list[str] = field(default_factory=list)
    common_failure_patterns: list[str] = field(default_factory=list)
    recovery_moves: list[str] = field(default_factory=list)
    completion_signals: list[str] = field(default_factory=list)
    positive_example_moves: list[str] = field(default_factory=list)
    negative_example_moves: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScenarioRecord:
    id: str
    title: str
    difficulty: str
    focus_subskills: list[str]
    doctor_persona_id: str
    max_turns: int
    success_criteria: list[str]
    failure_patterns: list[str]
    playbook: PlaybookRecord | None = None


@dataclass(frozen=True)
class CurriculumCompletionCriteriaRecord:
    required_scenario_ids: list[str]
    min_completed_sessions: int
    min_average_overall_score: float
    min_target_subskill_average: float


@dataclass(frozen=True)
class CurriculumStageRecord:
    id: str
    title: str
    description: str
    module_id: str
    scenario_ids: list[str]
    scenario_titles: dict[str, str]
    target_subskills: list[str]
    prerequisites: list[str]
    recommended_repetition: int
    completion_criteria: CurriculumCompletionCriteriaRecord


@dataclass(frozen=True)
class CurriculumModuleRecord:
    id: str
    title: str
    description: str
    stage_ids: list[str]


@dataclass(frozen=True)
class CurriculumRecord:
    id: str
    version: int
    title: str
    modules: dict[str, CurriculumModuleRecord]
    module_order: list[str]
    stages: dict[str, CurriculumStageRecord]
    stage_order: list[str]
    stage_index_by_id: dict[str, int]
    scenario_to_stage_id: dict[str, str]


@dataclass(frozen=True)
class DomainBundle:
    manifest: dict[str, Any]
    scenarios: dict[str, ScenarioRecord]
    personas: dict[str, dict[str, Any]]
    curriculum: CurriculumRecord
    skill_model: dict[str, Any]
    diagnosis_types: dict[str, Any]
    compliance_rules: dict[str, Any]
    score_schema: dict[str, Any]
    judge_review_schema: dict[str, Any]
    coach_feedback_schema: dict[str, Any]
    compliance_flags_schema: dict[str, Any]


REPO_ROOT = Path(__file__).resolve().parents[4]
DOMAIN_DIR = REPO_ROOT / "domains" / "mr_visit_jp"
SCHEMAS_DIR = REPO_ROOT / "packages" / "shared-schemas" / "schemas"
COMPLIANCE_SENSITIVE_KEYWORDS = (
    "adverse event",
    "report",
    "reporting",
    "escalation",
    "pharmacovigilance",
    "sop",
)
COMPLIANCE_RECOVERY_KEYWORDS = (
    "report",
    "reporting",
    "escalation",
    "protocol",
    "pharmacovigilance",
    "sop",
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:  # pragma: no cover - defensive path
        raise DomainAssetError(f"Failed to read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DomainAssetError(f"Expected JSON object in {path}")
    return payload


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = yaml.safe_load(f)
    except Exception as exc:  # pragma: no cover - defensive path
        raise DomainAssetError(f"Failed to read YAML {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DomainAssetError(f"Expected YAML object in {path}")
    return payload


def _validate_with_schema(schema: dict[str, Any], payload: dict[str, Any], source: Path) -> None:
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        path = ".".join(str(p) for p in first.path) or "<root>"
        raise DomainAssetError(f"Schema validation failed for {source} at {path}: {first.message}")


def _normalized_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [
        item.strip().lower()
        for item in values
        if isinstance(item, str) and item.strip()
    ]


def _text_contains_any(texts: list[str], keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for text in texts for keyword in keywords)


def _is_compliance_sensitive_scenario(
    *,
    scenario_id: str,
    payload: dict[str, Any],
    playbook_payload: dict[str, Any],
) -> bool:
    texts = [
        scenario_id.strip().lower(),
        str(playbook_payload.get("learning_objective", "")).strip().lower(),
        *_normalized_strings(payload.get("success_criteria", [])),
        *_normalized_strings(payload.get("failure_patterns", [])),
        *_normalized_strings(playbook_payload.get("expected_flow", [])),
        *_normalized_strings(playbook_payload.get("common_failure_patterns", [])),
    ]
    return _text_contains_any(texts, COMPLIANCE_SENSITIVE_KEYWORDS)


def _validate_playbook_payload(
    *,
    scenario_id: str,
    payload: dict[str, Any],
    playbook_payload: dict[str, Any],
) -> None:
    target_subskills = playbook_payload.get("target_subskills", [])
    focus_subskills = payload.get("focus_subskills", [])

    if len(target_subskills) < 2:
        raise DomainAssetError(
            f"Scenario `{scenario_id}` playbook must target at least 2 subskills"
        )

    if set(target_subskills) != set(focus_subskills):
        raise DomainAssetError(
            f"Scenario `{scenario_id}` playbook target_subskills must match focus_subskills"
        )

    if len(playbook_payload.get("common_failure_patterns", [])) < 3:
        raise DomainAssetError(
            f"Scenario `{scenario_id}` playbook must have at least 3 common_failure_patterns"
        )

    if not playbook_payload.get("positive_example_moves"):
        raise DomainAssetError(
            f"Scenario `{scenario_id}` playbook must have at least 1 positive_example_move"
        )

    if not playbook_payload.get("negative_example_moves"):
        raise DomainAssetError(
            f"Scenario `{scenario_id}` playbook must have at least 1 negative_example_move"
        )

    if _is_compliance_sensitive_scenario(
        scenario_id=scenario_id,
        payload=payload,
        playbook_payload=playbook_payload,
    ):
        recovery_texts = _normalized_strings(playbook_payload.get("recovery_moves", []))
        if not _text_contains_any(recovery_texts, COMPLIANCE_RECOVERY_KEYWORDS):
            raise DomainAssetError(
                f"Scenario `{scenario_id}` playbook must include a compliance-specific "
                "recovery or escalation move"
            )


def _load_persona_index() -> dict[str, dict[str, Any]]:
    personas_file = DOMAIN_DIR / "assets" / "personas" / "doctor_personas.yaml"
    payload = _read_yaml(personas_file)
    raw_personas = payload.get("personas")
    if not isinstance(raw_personas, list) or not raw_personas:
        raise DomainAssetError(f"`personas` must be a non-empty list in {personas_file}")

    persona_index: dict[str, dict[str, Any]] = {}
    for persona in raw_personas:
        if not isinstance(persona, dict):
            raise DomainAssetError(f"Invalid persona entry in {personas_file}")
        persona_id = persona.get("id")
        if not isinstance(persona_id, str) or not persona_id:
            raise DomainAssetError(f"Persona missing non-empty `id` in {personas_file}")
        if persona_id in persona_index:
            raise DomainAssetError(f"Duplicate persona id `{persona_id}` in {personas_file}")
        persona_index[persona_id] = persona
    return persona_index


def _load_scenarios(
    persona_index: dict[str, dict[str, Any]],
    scenario_schema: dict[str, Any],
    valid_subskills: set[str],
    *,
    scenarios_dir: Path | None = None,
) -> dict[str, ScenarioRecord]:
    scenarios_dir = scenarios_dir or (DOMAIN_DIR / "scenarios")
    scenario_files = sorted(scenarios_dir.glob("*.yaml"))
    if not scenario_files:
        raise DomainAssetError(f"No scenario files found under {scenarios_dir}")

    scenarios: dict[str, ScenarioRecord] = {}
    for scenario_file in scenario_files:
        payload = _read_yaml(scenario_file)
        _validate_with_schema(scenario_schema, payload, scenario_file)

        scenario_id = payload["id"]
        if scenario_id in scenarios:
            raise DomainAssetError(f"Duplicate scenario id `{scenario_id}`")
        if payload["doctor_persona_id"] not in persona_index:
            raise DomainAssetError(
                f"Scenario `{scenario_id}` references unknown doctor persona "
                f"`{payload['doctor_persona_id']}`"
            )
        unknown_subskills = sorted(set(payload["focus_subskills"]) - valid_subskills)
        if unknown_subskills:
            raise DomainAssetError(
                f"Scenario `{scenario_id}` has unknown subskills: {unknown_subskills}"
            )

        pb_data = payload.get("playbook")
        if not isinstance(pb_data, dict):
            raise DomainAssetError(f"Scenario `{scenario_id}` must define a playbook object")

        _validate_playbook_payload(
            scenario_id=scenario_id,
            payload=payload,
            playbook_payload=pb_data,
        )
        playbook = PlaybookRecord(
            learning_objective=pb_data["learning_objective"],
            target_subskills=list(pb_data["target_subskills"]),
            expected_flow=list(pb_data["expected_flow"]),
            key_discovery_questions=list(pb_data.get("key_discovery_questions", [])),
            acceptable_evidence_moves=list(pb_data.get("acceptable_evidence_moves", [])),
            common_failure_patterns=list(pb_data.get("common_failure_patterns", [])),
            recovery_moves=list(pb_data.get("recovery_moves", [])),
            completion_signals=list(pb_data.get("completion_signals", [])),
            positive_example_moves=list(pb_data.get("positive_example_moves", [])),
            negative_example_moves=list(pb_data.get("negative_example_moves", [])),
        )

        scenarios[scenario_id] = ScenarioRecord(
            id=payload["id"],
            title=payload["title"],
            difficulty=payload["difficulty"],
            focus_subskills=list(payload["focus_subskills"]),
            doctor_persona_id=payload["doctor_persona_id"],
            max_turns=payload["constraints"]["max_turns"],
            success_criteria=list(payload["success_criteria"]),
            failure_patterns=list(payload["failure_patterns"]),
            playbook=playbook,
        )

    return scenarios


def _load_curriculum(
    *,
    valid_subskills: set[str],
    scenarios: dict[str, ScenarioRecord],
) -> CurriculumRecord:
    curriculum_path = DOMAIN_DIR / "curriculum" / "core.yaml"
    curriculum_schema = _read_json(SCHEMAS_DIR / "mr_curriculum.schema.json")
    payload = _read_yaml(curriculum_path)
    _validate_with_schema(curriculum_schema, payload, curriculum_path)

    raw_modules = payload.get("modules")
    if not isinstance(raw_modules, list) or not raw_modules:
        raise DomainAssetError(f"`modules` must be a non-empty list in {curriculum_path}")

    modules: dict[str, CurriculumModuleRecord] = {}
    module_order: list[str] = []
    stages: dict[str, CurriculumStageRecord] = {}
    stage_order: list[str] = []
    scenario_to_stage_id: dict[str, str] = {}

    for raw_module in raw_modules:
        if not isinstance(raw_module, dict):
            raise DomainAssetError(f"Invalid curriculum module entry in {curriculum_path}")
        module_id = str(raw_module.get("id", "")).strip()
        if not module_id:
            raise DomainAssetError(f"Curriculum module is missing non-empty `id` in {curriculum_path}")
        if module_id in modules:
            raise DomainAssetError(f"Duplicate curriculum module id `{module_id}` in {curriculum_path}")

        stage_ids: list[str] = []
        raw_stages = raw_module.get("stages")
        if not isinstance(raw_stages, list) or not raw_stages:
            raise DomainAssetError(
                f"Curriculum module `{module_id}` must define a non-empty `stages` list"
            )

        for raw_stage in raw_stages:
            if not isinstance(raw_stage, dict):
                raise DomainAssetError(
                    f"Curriculum module `{module_id}` contains an invalid stage entry"
                )
            stage_id = str(raw_stage.get("id", "")).strip()
            if not stage_id:
                raise DomainAssetError(
                    f"Curriculum module `{module_id}` contains a stage without non-empty `id`"
                )
            if stage_id in stages:
                raise DomainAssetError(f"Duplicate curriculum stage id `{stage_id}` in {curriculum_path}")

            scenario_ids = [str(item).strip() for item in raw_stage.get("scenario_ids", [])]
            if not scenario_ids or any(not item for item in scenario_ids):
                raise DomainAssetError(
                    f"Curriculum stage `{stage_id}` must define non-empty `scenario_ids`"
                )
            missing_scenarios = [scenario_id for scenario_id in scenario_ids if scenario_id not in scenarios]
            if missing_scenarios:
                raise DomainAssetError(
                    f"Curriculum stage `{stage_id}` references unknown scenarios: {missing_scenarios}"
                )
            for scenario_id in scenario_ids:
                assigned_stage = scenario_to_stage_id.get(scenario_id)
                if assigned_stage is not None:
                    raise DomainAssetError(
                        f"Scenario `{scenario_id}` is assigned to multiple curriculum stages: "
                        f"`{assigned_stage}` and `{stage_id}`"
                    )
                scenario_to_stage_id[scenario_id] = stage_id

            target_subskills = [str(item).strip() for item in raw_stage.get("target_subskills", [])]
            if not target_subskills or any(not item for item in target_subskills):
                raise DomainAssetError(
                    f"Curriculum stage `{stage_id}` must define non-empty `target_subskills`"
                )
            unknown_subskills = sorted(set(target_subskills) - valid_subskills)
            if unknown_subskills:
                raise DomainAssetError(
                    f"Curriculum stage `{stage_id}` has unknown subskills: {unknown_subskills}"
                )

            prerequisites = [str(item).strip() for item in raw_stage.get("prerequisites", []) if str(item).strip()]
            recommended_repetition = int(raw_stage.get("recommended_repetition", 1))

            completion = raw_stage.get("completion_criteria")
            if not isinstance(completion, dict):
                raise DomainAssetError(
                    f"Curriculum stage `{stage_id}` must define a `completion_criteria` object"
                )
            required_scenario_ids = [
                str(item).strip()
                for item in completion.get("required_scenario_ids", [])
                if str(item).strip()
            ]
            if not required_scenario_ids:
                raise DomainAssetError(
                    f"Curriculum stage `{stage_id}` must define non-empty "
                    "`completion_criteria.required_scenario_ids`"
                )
            if not set(required_scenario_ids).issubset(set(scenario_ids)):
                raise DomainAssetError(
                    f"Curriculum stage `{stage_id}` completion criteria must be a subset of stage scenarios"
                )

            stage_record = CurriculumStageRecord(
                id=stage_id,
                title=str(raw_stage["title"]).strip(),
                description=str(raw_stage["description"]).strip(),
                module_id=module_id,
                scenario_ids=list(scenario_ids),
                scenario_titles={
                    scenario_id: scenarios[scenario_id].title
                    for scenario_id in scenario_ids
                },
                target_subskills=list(target_subskills),
                prerequisites=list(prerequisites),
                recommended_repetition=max(1, recommended_repetition),
                completion_criteria=CurriculumCompletionCriteriaRecord(
                    required_scenario_ids=list(required_scenario_ids),
                    min_completed_sessions=max(1, int(completion.get("min_completed_sessions", 1))),
                    min_average_overall_score=float(
                        completion.get("min_average_overall_score", 0.0)
                    ),
                    min_target_subskill_average=float(
                        completion.get("min_target_subskill_average", 0.0)
                    ),
                ),
            )
            stages[stage_id] = stage_record
            stage_ids.append(stage_id)
            stage_order.append(stage_id)

        modules[module_id] = CurriculumModuleRecord(
            id=module_id,
            title=str(raw_module["title"]).strip(),
            description=str(raw_module["description"]).strip(),
            stage_ids=stage_ids,
        )
        module_order.append(module_id)

    stage_index_by_id = {stage_id: index for index, stage_id in enumerate(stage_order)}
    for stage_id, stage in stages.items():
        for prerequisite in stage.prerequisites:
            if prerequisite not in stages:
                raise DomainAssetError(
                    f"Curriculum stage `{stage_id}` references unknown prerequisite `{prerequisite}`"
                )
            if prerequisite == stage_id:
                raise DomainAssetError(
                    f"Curriculum stage `{stage_id}` cannot depend on itself"
                )
            if stage_index_by_id[prerequisite] >= stage_index_by_id[stage_id]:
                raise DomainAssetError(
                    f"Curriculum stage `{stage_id}` prerequisites must come before the stage itself"
                )

    return CurriculumRecord(
        id=str(payload["curriculum_id"]).strip(),
        version=int(payload["version"]),
        title=str(payload["title"]).strip(),
        modules=modules,
        module_order=module_order,
        stages=stages,
        stage_order=stage_order,
        stage_index_by_id=stage_index_by_id,
        scenario_to_stage_id=scenario_to_stage_id,
    )


def load_domain_bundle() -> DomainBundle:
    manifest_schema = _read_json(SCHEMAS_DIR / "skill_manifest.schema.json")
    scenario_schema = _read_json(SCHEMAS_DIR / "mr_scenario.schema.json")

    manifest = _read_yaml(DOMAIN_DIR / "manifests" / "skill.yaml")
    _validate_with_schema(manifest_schema, manifest, DOMAIN_DIR / "manifests" / "skill.yaml")
    manifest_subskills = manifest.get("subskills")
    if not isinstance(manifest_subskills, list) or not manifest_subskills:
        raise DomainAssetError("Skill manifest must define a non-empty `subskills` list")
    valid_subskills = set(manifest_subskills)

    persona_index = _load_persona_index()
    scenarios = _load_scenarios(persona_index, scenario_schema, valid_subskills)
    curriculum = _load_curriculum(
        valid_subskills=valid_subskills,
        scenarios=scenarios,
    )

    skill_model = _read_yaml(DOMAIN_DIR / "rubrics" / "skill_model.yaml")
    skill_model_subskills = skill_model.get("subskills")
    if not isinstance(skill_model_subskills, dict):
        raise DomainAssetError("`skill_model.yaml` must include `subskills` mapping")
    if set(skill_model_subskills.keys()) != valid_subskills:
        raise DomainAssetError(
            "Mismatch between manifest subskills and skill_model subskills keys"
        )

    diagnosis_types = _read_yaml(DOMAIN_DIR / "rubrics" / "diagnosis_types.yaml")
    compliance_rules = _read_yaml(DOMAIN_DIR / "compliance" / "rules.yaml")
    score_schema = _read_json(DOMAIN_DIR / "rubrics" / "score_schema.json")
    judge_review_schema = _read_json(SCHEMAS_DIR / "judge_review.schema.json")
    coach_feedback_schema = _read_json(SCHEMAS_DIR / "coach_feedback.schema.json")
    compliance_flags_schema = _read_json(SCHEMAS_DIR / "compliance_flags.schema.json")

    return DomainBundle(
        manifest=manifest,
        scenarios=scenarios,
        personas=persona_index,
        curriculum=curriculum,
        skill_model=skill_model,
        diagnosis_types=diagnosis_types,
        compliance_rules=compliance_rules,
        score_schema=score_schema,
        judge_review_schema=judge_review_schema,
        coach_feedback_schema=coach_feedback_schema,
        compliance_flags_schema=compliance_flags_schema,
    )


@lru_cache(maxsize=1)
def get_domain_bundle() -> DomainBundle:
    return load_domain_bundle()

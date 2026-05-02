from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scenarios import asset_loader
from scenarios.asset_loader import CurriculumRecord, DomainAssetError


def _valid_curriculum_payload() -> dict[str, object]:
    return {
        "curriculum_id": "test_curriculum_v1",
        "version": 1,
        "title": "Test Curriculum",
        "modules": [
            {
                "id": "foundation",
                "title": "Foundation",
                "description": "Core entry skills.",
                "stages": [
                    {
                        "id": "stage_one",
                        "title": "Stage One",
                        "description": "Handle fast openings.",
                        "scenario_ids": [
                            "busy_doctor_short_visit",
                            "low_interest_doctor_intro_fail",
                        ],
                        "target_subskills": [
                            "opening",
                            "need_discovery",
                        ],
                        "prerequisites": [],
                        "recommended_repetition": 2,
                        "completion_criteria": {
                            "required_scenario_ids": [
                                "busy_doctor_short_visit",
                            ],
                            "min_completed_sessions": 1,
                            "min_average_overall_score": 60,
                            "min_target_subskill_average": 3.0,
                        },
                    },
                    {
                        "id": "stage_two",
                        "title": "Stage Two",
                        "description": "Re-enter prior rejection context.",
                        "scenario_ids": [
                            "revisit_after_prior_rejection",
                            "new_product_adoption_barrier",
                        ],
                        "target_subskills": [
                            "opening",
                            "profiling",
                            "need_discovery",
                        ],
                        "prerequisites": ["stage_one"],
                        "recommended_repetition": 2,
                        "completion_criteria": {
                            "required_scenario_ids": [
                                "revisit_after_prior_rejection",
                            ],
                            "min_completed_sessions": 1,
                            "min_average_overall_score": 65,
                            "min_target_subskill_average": 3.2,
                        },
                    },
                ],
            }
        ],
    }


def _write_curriculum(tmp_path: Path, payload: dict[str, object]) -> Path:
    domain_dir = tmp_path / "mr_visit_jp"
    curriculum_dir = domain_dir / "curriculum"
    curriculum_dir.mkdir(parents=True, exist_ok=True)
    curriculum_path = curriculum_dir / "core.yaml"
    curriculum_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    return domain_dir


def _load_curriculum_from_tmp(tmp_path: Path, payload: dict[str, object]) -> CurriculumRecord:
    bundle = asset_loader.load_domain_bundle()
    domain_dir = _write_curriculum(tmp_path, payload)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(asset_loader, "DOMAIN_DIR", domain_dir)
        return asset_loader._load_curriculum(
            valid_subskills=set(bundle.manifest["subskills"]),
            scenarios=bundle.scenarios,
        )


def test_real_curriculum_asset_loads_and_maps_all_scenarios() -> None:
    bundle = asset_loader.load_domain_bundle()

    assert bundle.curriculum.id == "mr_visit_jp_core_v1"
    assert bundle.curriculum.module_order == [
        "foundation_attention_and_relevance",
        "evidence_and_objection_progression",
    ]
    assert len(bundle.curriculum.stage_order) == 4
    assert set(bundle.curriculum.scenario_to_stage_id) == set(bundle.scenarios)


def test_load_curriculum_rejects_duplicate_stage_scenario_assignment(tmp_path: Path) -> None:
    payload = _valid_curriculum_payload()
    stage_two = payload["modules"][0]["stages"][1]
    stage_two["scenario_ids"] = [
        "busy_doctor_short_visit",
        "new_product_adoption_barrier",
    ]

    with pytest.raises(DomainAssetError, match="assigned to multiple curriculum stages"):
        _load_curriculum_from_tmp(tmp_path, payload)


def test_load_curriculum_rejects_prerequisite_that_points_forward(tmp_path: Path) -> None:
    payload = _valid_curriculum_payload()
    payload["modules"][0]["stages"][0]["prerequisites"] = ["stage_two"]

    with pytest.raises(
        DomainAssetError,
        match="prerequisites must come before the stage itself",
    ):
        _load_curriculum_from_tmp(tmp_path, payload)

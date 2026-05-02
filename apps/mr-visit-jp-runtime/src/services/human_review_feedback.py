from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from persistence.file_store_support import advisory_file_lock, atomic_write_text, load_jsonl_objects
from persistence.interfaces import SessionStore
from scenarios.asset_loader import DomainBundle
from services.evaluation_fixture_dataset import (
    ALLOWED_FIXTURE_BUCKETS,
    KNOWN_COMPLIANCE_CASES,
    KNOWN_FINISH_REASONS,
)


HUMAN_REVIEW_SCHEMA_VERSION = 1
HUMAN_REVIEW_DOMAIN_ID = "mr_visit_jp"
ALLOWED_REVIEWER_ROLES = {"sme", "trainer"}
ALLOWED_VERDICTS = {"accept_ai_review", "correct_ai_review"}
DEFAULT_FIXTURE_BUCKET = "medium"


class HumanReviewFeedbackError(RuntimeError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _non_empty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HumanReviewFeedbackError(label)
    return value.strip()


def _optional_non_empty_string(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, label=label)


def _string_list(value: Any, *, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HumanReviewFeedbackError(label)
    output: list[str] = []
    for item in value:
        output.append(_non_empty_string(item, label=label))
    return output


def _int_map(value: Any, *, label: str) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise HumanReviewFeedbackError(label)
    normalized: dict[str, int] = {}
    for key, raw_score in value.items():
        subskill_id = _non_empty_string(key, label=f"{label} key must be non-empty")
        if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
            raise HumanReviewFeedbackError(f"{label}.{subskill_id} must be numeric")
        score = int(raw_score)
        if score < 0 or score > 5:
            raise HumanReviewFeedbackError(f"{label}.{subskill_id} must be in range 0..5")
        normalized[subskill_id] = score
    return normalized


def _bool_map(value: Any, *, label: str) -> dict[str, bool]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise HumanReviewFeedbackError(label)
    normalized: dict[str, bool] = {}
    for key, raw_bool in value.items():
        evidence_id = _non_empty_string(key, label=f"{label} key must be non-empty")
        if not isinstance(raw_bool, bool):
            raise HumanReviewFeedbackError(f"{label}.{evidence_id} must be boolean")
        normalized[evidence_id] = raw_bool
    return normalized


def _normalize_compliance_severity_overrides(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HumanReviewFeedbackError("compliance_severity_overrides must be a list")
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise HumanReviewFeedbackError(
                f"compliance_severity_overrides[{index}] must be an object"
            )
        rule_id = _non_empty_string(
            item.get("rule_id"),
            label=f"compliance_severity_overrides[{index}].rule_id is required",
        )
        severity = _non_empty_string(
            item.get("severity"),
            label=f"compliance_severity_overrides[{index}].severity is required",
        ).lower()
        rationale = _optional_non_empty_string(
            item.get("rationale"),
            label=f"compliance_severity_overrides[{index}].rationale must be non-empty when present",
        )
        normalized_item = {"rule_id": rule_id, "severity": severity}
        if rationale is not None:
            normalized_item["rationale"] = rationale
        normalized.append(normalized_item)
    return normalized


def _normalize_fixture_promotion(value: Any, *, scenario_id: str) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    include = bool(payload.get("include", False))
    bucket_raw = payload.get("bucket")
    bucket = None
    if bucket_raw is not None:
        bucket = _non_empty_string(bucket_raw, label="fixture_promotion.bucket must be non-empty")
        if bucket not in ALLOWED_FIXTURE_BUCKETS:
            raise HumanReviewFeedbackError(
                f"fixture_promotion.bucket must be one of {list(ALLOWED_FIXTURE_BUCKETS)}"
            )
    name_hint = _optional_non_empty_string(
        payload.get("name_hint"),
        label="fixture_promotion.name_hint must be non-empty when present",
    )
    scenario_ids = _string_list(
        payload.get("scenario_ids"),
        label="fixture_promotion.scenario_ids must be a list",
    )
    if not scenario_ids:
        scenario_ids = [scenario_id]
    focus_subskills = _string_list(
        payload.get("focus_subskills"),
        label="fixture_promotion.focus_subskills must be a list",
    )
    compliance_case = _optional_non_empty_string(
        payload.get("compliance_case"),
        label="fixture_promotion.compliance_case must be non-empty when present",
    )
    if compliance_case is None:
        compliance_case = "none"
    if compliance_case not in KNOWN_COMPLIANCE_CASES:
        raise HumanReviewFeedbackError(
            f"fixture_promotion.compliance_case must be one of {list(KNOWN_COMPLIANCE_CASES)}"
        )
    finish_reason = _optional_non_empty_string(
        payload.get("finish_reason"),
        label="fixture_promotion.finish_reason must be non-empty when present",
    )
    if finish_reason is not None and finish_reason not in KNOWN_FINISH_REASONS:
        raise HumanReviewFeedbackError(
            f"fixture_promotion.finish_reason must be one of {list(KNOWN_FINISH_REASONS)}"
        )
    tags = _string_list(
        payload.get("tags"),
        label="fixture_promotion.tags must be a list",
    )
    return {
        "include": include,
        "bucket": bucket,
        "name_hint": name_hint,
        "scenario_ids": scenario_ids,
        "focus_subskills": focus_subskills,
        "compliance_case": compliance_case,
        "finish_reason": finish_reason,
        "tags": tags,
    }


def _review_hash(review: dict[str, Any]) -> str:
    encoded = json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _latest_record_by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["record_id"])].append(record)
    return {
        record_id: max(items, key=lambda item: int(item["version"]))
        for record_id, items in grouped.items()
    }


class HumanReviewFeedbackService:
    def __init__(
        self,
        *,
        root_dir: Path,
        session_store: SessionStore,
        domain_bundle: DomainBundle,
    ) -> None:
        self._root_dir = Path(root_dir)
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._session_store = session_store
        self._bundle = domain_bundle
        self._lock = Lock()

    def list_records(
        self,
        *,
        org_id: str | None = None,
        session_id: str | None = None,
        latest_only: bool = False,
    ) -> list[dict[str, Any]]:
        records = self._read_records(org_id=org_id)
        if latest_only:
            records = list(_latest_record_by_id(records).values())
        if session_id:
            records = [item for item in records if str(item.get("session_id")) == session_id]
        return sorted(
            records,
            key=lambda item: (
                str(item.get("record_id", "")),
                int(item.get("version", 0)),
            ),
        )

    def create_record(
        self,
        payload: dict[str, Any],
        *,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        session_id = _non_empty_string(payload.get("session_id"), label="session_id is required")
        reviewer_id = _non_empty_string(payload.get("reviewer_id"), label="reviewer_id is required")
        reviewer_role = _non_empty_string(
            payload.get("reviewer_role", "sme"),
            label="reviewer_role is required",
        ).lower()
        if reviewer_role not in ALLOWED_REVIEWER_ROLES:
            raise HumanReviewFeedbackError(
                f"reviewer_role must be one of {sorted(ALLOWED_REVIEWER_ROLES)}"
            )
        verdict = _non_empty_string(payload.get("verdict"), label="verdict is required").lower()
        if verdict not in ALLOWED_VERDICTS:
            raise HumanReviewFeedbackError(f"verdict must be one of {sorted(ALLOWED_VERDICTS)}")

        session_payload = self._session_store.get(session_id, org_id=org_id)
        if not isinstance(session_payload, dict):
            raise HumanReviewFeedbackError(f"Unknown session_id `{session_id}`")
        if str(session_payload.get("status", "")) != "finalized":
            raise HumanReviewFeedbackError(
                f"session_id `{session_id}` is not finalized; feedback requires finalized review"
            )
        review = session_payload.get("review")
        if not isinstance(review, dict):
            raise HumanReviewFeedbackError(
                f"session_id `{session_id}` does not have a structured review payload"
            )

        record_id_input = _optional_non_empty_string(
            payload.get("record_id"),
            label="record_id must be non-empty when present",
        )
        supersedes_version = payload.get("supersedes_version")
        if supersedes_version is not None and (
            isinstance(supersedes_version, bool) or not isinstance(supersedes_version, (int, float))
        ):
            raise HumanReviewFeedbackError("supersedes_version must be numeric when present")

        subskill_score_overrides = _int_map(
            payload.get("subskill_score_overrides"),
            label="subskill_score_overrides must be an object",
        )
        diagnosis_add_ids = _string_list(
            payload.get("diagnosis_add_ids"),
            label="diagnosis_add_ids must be a list",
        )
        diagnosis_remove_ids = _string_list(
            payload.get("diagnosis_remove_ids"),
            label="diagnosis_remove_ids must be a list",
        )
        compliance_severity_overrides = _normalize_compliance_severity_overrides(
            payload.get("compliance_severity_overrides")
        )
        evidence_sufficiency = _bool_map(
            payload.get("evidence_sufficiency"),
            label="evidence_sufficiency must be an object",
        )
        sme_comment = _optional_non_empty_string(
            payload.get("sme_comment"),
            label="sme_comment must be non-empty when present",
        )
        fixture_promotion = _normalize_fixture_promotion(
            payload.get("fixture_promotion"),
            scenario_id=str(session_payload.get("scenario_id", "")),
        )

        with self._lock:
            records = self._read_records(org_id=org_id)
            latest_by_id = _latest_record_by_id(records)

            record_id: str
            version: int
            supersedes_version_value: int | None
            if record_id_input is None:
                record_id = f"hrf_{uuid4().hex[:12]}"
                version = 1
                supersedes_version_value = None
            else:
                record_id = record_id_input
                existing = latest_by_id.get(record_id)
                if existing is None:
                    version = 1
                    supersedes_version_value = None
                else:
                    latest_version = int(existing["version"])
                    provided_supersedes = int(supersedes_version) if supersedes_version is not None else None
                    if provided_supersedes != latest_version:
                        raise HumanReviewFeedbackError(
                            f"record_id `{record_id}` latest version is {latest_version}; "
                            "supersedes_version must match latest version for append-only updates"
                        )
                    version = latest_version + 1
                    supersedes_version_value = latest_version

            record = {
                "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
                "domain_id": HUMAN_REVIEW_DOMAIN_ID,
                "record_id": record_id,
                "version": version,
                "supersedes_version": supersedes_version_value,
                "session_id": session_id,
                "scenario_id": str(session_payload.get("scenario_id", "")),
                "learner_id": str(session_payload.get("learner_id", "")),
                "review_snapshot": {
                    "updated_at": str(session_payload.get("updated_at", "")),
                    "prompt_profile": str(
                        (
                            review.get("meta", {}).get("prompting", {}).get("profile_id")
                            if isinstance(review.get("meta"), dict)
                            else ""
                        )
                        or ""
                    ),
                    "overall_score": int(review.get("overall_score", 0)),
                    "overall_band": str(review.get("overall_band", "")),
                    "review_hash": _review_hash(review),
                },
                "reviewer": {
                    "reviewer_id": reviewer_id,
                    "reviewer_role": reviewer_role,
                },
                "verdict": verdict,
                "corrections": {
                    "subskill_score_overrides": subskill_score_overrides,
                    "diagnosis_add_ids": diagnosis_add_ids,
                    "diagnosis_remove_ids": diagnosis_remove_ids,
                    "compliance_severity_overrides": compliance_severity_overrides,
                    "evidence_sufficiency": evidence_sufficiency,
                    "sme_comment": sme_comment,
                },
                "fixture_promotion": fixture_promotion,
                "created_at": _utc_now_iso(),
            }

            records.append(record)
            self._write_records(records, org_id=org_id)
            return record

    def export_bundle(
        self,
        *,
        org_id: str | None = None,
        session_id: str | None = None,
        latest_only: bool = False,
    ) -> dict[str, Any]:
        records = self.list_records(
            org_id=org_id,
            session_id=session_id,
            latest_only=latest_only,
        )
        return {
            "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
            "domain_id": HUMAN_REVIEW_DOMAIN_ID,
            "exported_at": _utc_now_iso(),
            "record_count": len(records),
            "records": records,
        }

    def import_bundle(
        self,
        bundle: dict[str, Any],
        *,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(bundle, dict):
            raise HumanReviewFeedbackError("import payload must be an object")
        if int(bundle.get("schema_version", 0)) != HUMAN_REVIEW_SCHEMA_VERSION:
            raise HumanReviewFeedbackError(
                f"import schema_version must be {HUMAN_REVIEW_SCHEMA_VERSION}"
            )
        domain_id = _non_empty_string(bundle.get("domain_id"), label="domain_id is required")
        if domain_id != HUMAN_REVIEW_DOMAIN_ID:
            raise HumanReviewFeedbackError(
                f"domain_id must be `{HUMAN_REVIEW_DOMAIN_ID}` for this runtime"
            )
        records_raw = bundle.get("records")
        if not isinstance(records_raw, list):
            raise HumanReviewFeedbackError("records must be a list")

        with self._lock:
            current = self._read_records(org_id=org_id)
            existing_keys = {
                (str(item["record_id"]), int(item["version"]))
                for item in current
            }
            imported = 0
            skipped_duplicates = 0
            for index, item in enumerate(records_raw, start=1):
                normalized = self._normalize_imported_record(item, index=index)
                key = (str(normalized["record_id"]), int(normalized["version"]))
                if key in existing_keys:
                    skipped_duplicates += 1
                    continue
                current.append(normalized)
                existing_keys.add(key)
                imported += 1
            if imported > 0:
                self._write_records(current, org_id=org_id)

        return {
            "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
            "imported_count": imported,
            "skipped_duplicate_count": skipped_duplicates,
            "total_count": imported + skipped_duplicates,
        }

    def build_fixture_candidates(
        self,
        *,
        org_id: str | None = None,
        latest_only: bool = True,
    ) -> dict[str, Any]:
        records = self.list_records(org_id=org_id, latest_only=latest_only)
        candidates: list[dict[str, Any]] = []
        skipped_count = 0

        for record in records:
            promotion = record.get("fixture_promotion", {})
            if not isinstance(promotion, dict) or not bool(promotion.get("include", False)):
                continue
            session_id = str(record.get("session_id", ""))
            session_payload = self._session_store.get(session_id, org_id=org_id)
            if not isinstance(session_payload, dict):
                skipped_count += 1
                candidates.append(
                    {
                        "candidate_id": f"{record['record_id']}:v{record['version']}",
                        "record_id": record["record_id"],
                        "version": record["version"],
                        "ready": False,
                        "reason": f"session `{session_id}` not found",
                    }
                )
                continue

            turns = session_payload.get("turns")
            if not isinstance(turns, list) or not turns:
                skipped_count += 1
                candidates.append(
                    {
                        "candidate_id": f"{record['record_id']}:v{record['version']}",
                        "record_id": record["record_id"],
                        "version": record["version"],
                        "ready": False,
                        "reason": f"session `{session_id}` has no turns",
                    }
                )
                continue

            review = session_payload.get("review")
            if not isinstance(review, dict):
                skipped_count += 1
                candidates.append(
                    {
                        "candidate_id": f"{record['record_id']}:v{record['version']}",
                        "record_id": record["record_id"],
                        "version": record["version"],
                        "ready": False,
                        "reason": f"session `{session_id}` has no structured review",
                    }
                )
                continue

            scenario_id = str(record.get("scenario_id", ""))
            scenario = self._bundle.scenarios.get(scenario_id)
            if scenario is None:
                skipped_count += 1
                candidates.append(
                    {
                        "candidate_id": f"{record['record_id']}:v{record['version']}",
                        "record_id": record["record_id"],
                        "version": record["version"],
                        "ready": False,
                        "reason": f"unknown scenario_id `{scenario_id}`",
                    }
                )
                continue

            corrections = record.get("corrections", {})
            subskill_scores = (
                corrections.get("subskill_score_overrides", {})
                if isinstance(corrections, dict)
                else {}
            )
            if not isinstance(subskill_scores, dict):
                subskill_scores = {}

            focus_subskills = promotion.get("focus_subskills", [])
            if not isinstance(focus_subskills, list) or not focus_subskills:
                focus_subskills = list(scenario.focus_subskills)

            overall_score = int(review.get("overall_score", 0))
            score_min = max(0, overall_score - 5)
            score_max = min(100, overall_score + 5)
            overall_band = str(review.get("overall_band", "functional"))
            diagnosis_add_ids = (
                corrections.get("diagnosis_add_ids", [])
                if isinstance(corrections, dict)
                else []
            )
            diagnosis_remove_ids = (
                corrections.get("diagnosis_remove_ids", [])
                if isinstance(corrections, dict)
                else []
            )
            compliance_overrides = (
                corrections.get("compliance_severity_overrides", [])
                if isinstance(corrections, dict)
                else []
            )
            required_rule_ids = sorted(
                {
                    str(item.get("rule_id", "")).strip()
                    for item in compliance_overrides
                    if isinstance(item, dict) and str(item.get("rule_id", "")).strip()
                }
            )
            required_severities = sorted(
                {
                    str(item.get("severity", "")).strip()
                    for item in compliance_overrides
                    if isinstance(item, dict)
                    and str(item.get("severity", "")).strip() in {"high", "critical"}
                }
            )

            required_subskill_score_min = {key: int(value) for key, value in subskill_scores.items()}
            required_subskill_score_max = {key: int(value) for key, value in subskill_scores.items()}

            name_hint = promotion.get("name_hint")
            if isinstance(name_hint, str) and name_hint.strip():
                fixture_name = name_hint.strip()
            else:
                fixture_name = f"{scenario_id}_{record['record_id']}_v{record['version']}"

            raw_turns: list[dict[str, Any]] = []
            for turn in turns:
                if not isinstance(turn, dict):
                    continue
                raw_turns.append(
                    {
                        "user_message": str(turn.get("user_message", "")),
                        "director_events": list(turn.get("director_events", [])),
                    }
                )

            finish_reason = promotion.get("finish_reason")
            if not isinstance(finish_reason, str) or not finish_reason:
                finish_reason = str(session_payload.get("finish_reason") or "manual_finish")
            if finish_reason not in KNOWN_FINISH_REASONS:
                finish_reason = "manual_finish"

            fixture_bucket = promotion.get("bucket")
            if not isinstance(fixture_bucket, str) or not fixture_bucket:
                fixture_bucket = DEFAULT_FIXTURE_BUCKET

            tags = promotion.get("tags", [])
            if not isinstance(tags, list):
                tags = []

            candidate = {
                "candidate_id": f"{record['record_id']}:v{record['version']}",
                "record_id": record["record_id"],
                "version": record["version"],
                "session_id": session_id,
                "scenario_id": scenario_id,
                "ready": True,
                "fixture_path": f"{fixture_bucket}/{fixture_name}.json",
                "fixture": {
                    "name": fixture_name,
                    "finish_reason": finish_reason,
                    "scenario_focus_subskills": focus_subskills,
                    "turns": raw_turns,
                    "expected": {
                        "overall_score_min": score_min,
                        "overall_score_max": score_max,
                        "overall_band_one_of": [overall_band],
                        "required_diagnosis_ids": list(diagnosis_add_ids),
                        "forbidden_diagnosis_ids": list(diagnosis_remove_ids),
                        "required_compliance_rule_ids": required_rule_ids,
                        "required_compliance_severities": required_severities,
                        "forbidden_compliance_severities": ["critical"],
                        "required_subskill_score_min": required_subskill_score_min,
                        "required_subskill_score_max": required_subskill_score_max,
                    },
                    "metadata": {
                        "schema_version": 1,
                        "scenario_ids": list(
                            promotion.get("scenario_ids", [scenario_id])
                            if isinstance(promotion.get("scenario_ids"), list)
                            else [scenario_id]
                        ),
                        "compliance_case": str(promotion.get("compliance_case", "none")),
                        "tags": list(tags) if tags else ["sme_feedback", "candidate_fixture"],
                    },
                },
            }
            candidates.append(candidate)

        return {
            "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
            "domain_id": HUMAN_REVIEW_DOMAIN_ID,
            "generated_at": _utc_now_iso(),
            "candidate_count": len(candidates),
            "skipped_count": skipped_count,
            "candidates": candidates,
        }

    def _normalize_imported_record(self, payload: Any, *, index: int) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise HumanReviewFeedbackError(f"records[{index}] must be an object")
        if int(payload.get("schema_version", 0)) != HUMAN_REVIEW_SCHEMA_VERSION:
            raise HumanReviewFeedbackError(
                f"records[{index}].schema_version must be {HUMAN_REVIEW_SCHEMA_VERSION}"
            )
        if _non_empty_string(payload.get("domain_id"), label=f"records[{index}].domain_id is required") != HUMAN_REVIEW_DOMAIN_ID:
            raise HumanReviewFeedbackError(
                f"records[{index}].domain_id must be `{HUMAN_REVIEW_DOMAIN_ID}`"
            )
        record_id = _non_empty_string(
            payload.get("record_id"),
            label=f"records[{index}].record_id is required",
        )
        version_raw = payload.get("version")
        if isinstance(version_raw, bool) or not isinstance(version_raw, (int, float)):
            raise HumanReviewFeedbackError(f"records[{index}].version must be numeric")
        version = int(version_raw)
        if version < 1:
            raise HumanReviewFeedbackError(f"records[{index}].version must be >= 1")
        session_id = _non_empty_string(
            payload.get("session_id"),
            label=f"records[{index}].session_id is required",
        )
        verdict = _non_empty_string(
            payload.get("verdict"),
            label=f"records[{index}].verdict is required",
        ).lower()
        if verdict not in ALLOWED_VERDICTS:
            raise HumanReviewFeedbackError(
                f"records[{index}].verdict must be one of {sorted(ALLOWED_VERDICTS)}"
            )
        created_at = _non_empty_string(
            payload.get("created_at"),
            label=f"records[{index}].created_at is required",
        )

        # Import keeps original payload for auditability after required keys validate.
        normalized = dict(payload)
        normalized["record_id"] = record_id
        normalized["version"] = version
        normalized["session_id"] = session_id
        normalized["verdict"] = verdict
        normalized["created_at"] = created_at
        return normalized

    def _records_path(self, *, org_id: str | None = None) -> Path:
        base = self._root_dir
        if org_id:
            org_normalized = _non_empty_string(org_id, label="org_id must be non-empty")
            if "/" in org_normalized or "\\" in org_normalized:
                raise HumanReviewFeedbackError("org_id cannot contain path separators")
            base = base / org_normalized
        return base / "records.jsonl"

    def _read_records(self, *, org_id: str | None = None) -> list[dict[str, Any]]:
        path = self._records_path(org_id=org_id)
        if not path.exists():
            return []
        with advisory_file_lock(path):
            return load_jsonl_objects(
                path,
                entity_name="human_review_feedback",
                identifier_name="scope",
                identifier_value=org_id or "default",
                error_type=HumanReviewFeedbackError,
            )

    def _write_records(self, records: list[dict[str, Any]], *, org_id: str | None = None) -> None:
        path = self._records_path(org_id=org_id)
        with advisory_file_lock(path):
            atomic_write_text(
                path,
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
            )

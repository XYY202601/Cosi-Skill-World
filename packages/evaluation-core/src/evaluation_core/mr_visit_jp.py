from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from evaluation_core.benchmarks import get_peer_benchmark


SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}
MAX_EVIDENCE_ITEMS = 3
MAX_EVIDENCE_TEXT_LENGTH = 280
MAX_EVIDENCE_TAGS = 4


@dataclass(frozen=True)
class ReviewBuildInputs:
    turns: list[dict[str, Any]]
    turn_count: int
    finish_reason: str
    scenario_focus_subskills: list[str]
    subskill_weights: dict[str, float]
    skill_model: dict[str, Any]
    diagnosis_types: dict[str, Any]
    compliance_rules: dict[str, Any]
    score_schema: dict[str, Any]
    judge_review_schema: dict[str, Any]
    coach_feedback_schema: dict[str, Any]
    compliance_flags_schema: dict[str, Any]
    model_artifacts: dict[str, Any] | None = None
    model_error: str | None = None
    model_meta: dict[str, Any] | None = None
    prompting_meta: dict[str, Any] | None = None
    continuity_context: dict[str, Any] | None = None
    scenario_id: str | None = None


def _validate_schema(
    *,
    schema: dict[str, Any],
    payload: Any,
    label: str,
) -> None:
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
    if not errors:
        return
    first = errors[0]
    path = ".".join(str(p) for p in first.path) or "<root>"
    raise ValueError(f"{label} failed schema validation at {path}: {first.message}")


def _clamp_int(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(max_value, int(value)))


def _clean_text(value: Any, *, max_length: int = MAX_EVIDENCE_TEXT_LENGTH) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())[:max_length].strip()


def _normalize_turn_index(value: Any, *, fallback: int | None = None) -> int | None:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and value.is_integer() and value > 0:
        return int(value)
    return fallback


def _normalize_evidence_item(raw: Any) -> str | dict[str, Any] | None:
    if isinstance(raw, str):
        text = _clean_text(raw)
        return text or None

    if not isinstance(raw, dict):
        return None

    summary = _clean_text(raw.get("summary") or raw.get("excerpt") or "")
    if not summary:
        return None

    normalized: dict[str, Any] = {"summary": summary}

    turn_index = _normalize_turn_index(raw.get("turn_index"))
    if turn_index is not None:
        normalized["turn_index"] = turn_index

    speaker = raw.get("speaker")
    if speaker in {"learner", "doctor", "system"}:
        normalized["speaker"] = speaker

    excerpt = _clean_text(raw.get("excerpt"))
    if excerpt:
        normalized["excerpt"] = excerpt

    raw_tags = raw.get("tags", [])
    if isinstance(raw_tags, list):
        tags: list[str] = []
        for item in raw_tags:
            tag = _clean_text(item, max_length=64)
            if tag and tag not in tags:
                tags.append(tag)
        if tags:
            normalized["tags"] = tags[:MAX_EVIDENCE_TAGS]

    return normalized


def _normalize_evidence_list(raw_items: Any) -> list[str | dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []

    normalized: list[str | dict[str, Any]] = []
    for item in raw_items:
        normalized_item = _normalize_evidence_item(item)
        if normalized_item is None:
            continue
        normalized.append(normalized_item)
        if len(normalized) >= MAX_EVIDENCE_ITEMS:
            break
    return normalized


def _evidence_has_turn_reference(item: str | dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    turn_index = item.get("turn_index")
    return isinstance(turn_index, int) and turn_index > 0


def _evidence_identity(item: str | dict[str, Any]) -> tuple[Any, ...]:
    if isinstance(item, str):
        return ("string", item)
    return (
        "object",
        item.get("turn_index"),
        item.get("summary"),
        item.get("excerpt"),
    )


def _turn_has_any_event(turn: dict[str, Any], events: set[str]) -> bool:
    turn_events = turn.get("director_events", [])
    return isinstance(turn_events, list) and any(event in events for event in turn_events)


def _find_turn(
    turns: list[dict[str, Any]],
    predicate,
) -> dict[str, Any] | None:
    for turn in turns:
        if predicate(turn):
            return turn
    return None


def _structured_evidence(
    *,
    turn: dict[str, Any],
    summary: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    evidence = {
        "summary": _clean_text(summary),
        "turn_index": int(turn["turn_index"]),
        "speaker": "learner",
    }
    excerpt = _clean_text(turn.get("user_message", ""))
    if excerpt:
        evidence["excerpt"] = excerpt
    if tags:
        clean_tags = []
        for item in tags:
            tag = _clean_text(item, max_length=64)
            if tag and tag not in clean_tags:
                clean_tags.append(tag)
        if clean_tags:
            evidence["tags"] = clean_tags[:MAX_EVIDENCE_TAGS]
    return evidence


def _derived_turn_evidence(
    *,
    subskill_id: str,
    turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not turns:
        return []

    first_turn = turns[0]
    last_turn = turns[-1]
    question_turn = _find_turn(turns, lambda turn: "?" in str(turn.get("user_message", "")))
    evidence_turn = _find_turn(
        turns,
        lambda turn: (
            "evidence" in str(turn.get("message_lc", ""))
            or "study" in str(turn.get("message_lc", ""))
            or _turn_has_any_event(
                turn,
                {
                    "evidence_not_addressed",
                    "carryover_evidence_gap",
                    "evidence_detail_missing",
                    "evidence_dump_without_use_case",
                    "unsupported_claim_without_evidence",
                },
            )
        ),
    )
    low_info_turn = _find_turn(
        turns,
        lambda turn: _turn_has_any_event(turn, {"low_information_turn"}),
    )
    opening_issue_turn = _find_turn(
        turns,
        lambda turn: _turn_has_any_event(
            turn,
            {
                "opening_overlong",
                "opening_missing_permission",
                "carryover_opening_gap",
                "time_pressure_not_respected",
            },
        ),
    )
    followup_turn = _find_turn(
        turns,
        lambda turn: any(
            keyword in str(turn.get("message_lc", ""))
            for keyword in ("next step", "follow up", "follow-up", "followup")
        ),
    )
    need_turn = _find_turn(
        turns,
        lambda turn: (
            "?" in str(turn.get("user_message", ""))
            or any(
                keyword in str(turn.get("message_lc", ""))
                for keyword in (
                    "patient",
                    "profile",
                    "need",
                    "decision criteria",
                    "concern",
                    "barrier",
                )
            )
        ),
    )
    objection_turn = _find_turn(
        turns,
        lambda turn: (
            _turn_has_any_event(
                turn,
                {
                    "evidence_not_addressed",
                    "carryover_evidence_gap",
                    "unsupported_claim_without_evidence",
                },
            )
            or any(
                keyword in str(turn.get("message_lc", ""))
                for keyword in ("concern", "objection", "hesitation", "understand")
            )
        ),
    )

    if subskill_id == "preparation":
        focus_turn = low_info_turn or first_turn
        summary = (
            "This turn shows limited visit setup and reduced preparation depth."
            if focus_turn is low_info_turn
            else "This opening turn anchors the initial context used for the preparation score."
        )
        return [_structured_evidence(turn=focus_turn, summary=summary, tags=["preparation"])]

    if subskill_id == "opening":
        focus_turn = opening_issue_turn or first_turn
        summary = (
            "This opening did not secure a concise permission-based start."
            if focus_turn is opening_issue_turn
            else "This opening establishes permission or relevance early in the visit."
        )
        return [_structured_evidence(turn=focus_turn, summary=summary, tags=["opening"])]

    if subskill_id == "profiling":
        focus_turn = question_turn or first_turn
        summary = (
            "This turn asks for doctor or patient context before more detail delivery."
            if focus_turn is question_turn
            else "The visit moved ahead here without a targeted profiling question."
        )
        return [_structured_evidence(turn=focus_turn, summary=summary, tags=["profiling"])]

    if subskill_id == "scientific_delivery":
        focus_turn = evidence_turn or first_turn
        summary = (
            "This turn is the clearest evidence-linked message in the transcript."
            if focus_turn is evidence_turn
            else "The transcript contains limited evidence framing beyond this turn."
        )
        return [_structured_evidence(turn=focus_turn, summary=summary, tags=["scientific_delivery"])]

    if subskill_id == "need_discovery":
        focus_turn = need_turn or low_info_turn or first_turn
        summary = (
            "This turn probes the doctor's need, context, or decision criteria."
            if focus_turn is need_turn
            else "This turn stayed broad, so the doctor's unmet need remained unclear."
        )
        return [_structured_evidence(turn=focus_turn, summary=summary, tags=["need_discovery"])]

    if subskill_id == "objection_handling":
        focus_turn = objection_turn or evidence_turn or last_turn
        summary = (
            "This turn is where the objection response needed more direct acknowledgement and support."
            if focus_turn is objection_turn
            else "This turn carried the response burden but did not clearly resolve resistance."
        )
        return [_structured_evidence(turn=focus_turn, summary=summary, tags=["objection_handling"])]

    if subskill_id == "closing_followup":
        focus_turn = followup_turn or last_turn
        summary = (
            "This turn sets an explicit next step or follow-up."
            if focus_turn is followup_turn
            else "The close ended here without a concrete next-step commitment."
        )
        return [_structured_evidence(turn=focus_turn, summary=summary, tags=["closing_followup"])]

    return []


def _link_subskill_evidence_to_turns(
    *,
    subskills: dict[str, dict[str, Any]],
    turn_features: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    turns = turn_features.get("turns", [])
    if not isinstance(turns, list) or not turns:
        return subskills

    linked: dict[str, dict[str, Any]] = {}
    for subskill_id, payload in subskills.items():
        raw_evidence = payload.get("evidence", [])
        evidence = _normalize_evidence_list(raw_evidence)
        if not any(_evidence_has_turn_reference(item) for item in evidence):
            derived = _derived_turn_evidence(subskill_id=subskill_id, turns=turns)
            merged: list[str | dict[str, Any]] = []
            seen: set[tuple[Any, ...]] = set()
            for item in [*derived, *evidence]:
                item_id = _evidence_identity(item)
                if item_id in seen:
                    continue
                seen.add(item_id)
                merged.append(item)
                if len(merged) >= MAX_EVIDENCE_ITEMS:
                    break
            evidence = merged
        if not evidence:
            evidence = ["No evidence provided."]
        linked[subskill_id] = {**payload, "evidence": evidence[:MAX_EVIDENCE_ITEMS]}
    return linked


def _overall_band(overall_score: int, skill_model: dict[str, Any]) -> str:
    band_entries = (
        skill_model.get("overall_score", {}).get("bands", [])
        if isinstance(skill_model, dict)
        else []
    )
    if isinstance(band_entries, list):
        for band in band_entries:
            if not isinstance(band, dict):
                continue
            min_v = int(band.get("min", 0))
            max_v = int(band.get("max", 0))
            band_id = band.get("id")
            if isinstance(band_id, str) and min_v <= overall_score <= max_v:
                return band_id

    if overall_score <= 39:
        return "critical_gap"
    if overall_score <= 59:
        return "emerging"
    if overall_score <= 74:
        return "functional"
    if overall_score <= 89:
        return "strong"
    return "excellent"


def _collect_turn_features(turns: list[dict[str, Any]]) -> dict[str, Any]:
    opening_overlong_count = 0
    low_info_count = 0
    evidence_not_addressed_count = 0
    opening_missing_permission_count = 0
    weak_profiling_count = 0
    carryover_opening_gap = False
    carryover_profiling_gap = False
    carryover_evidence_gap = False
    carryover_closing_gap = False
    has_question = False
    has_evidence_keyword = False
    has_next_step_keyword = False

    user_messages: list[str] = []
    turn_snapshots: list[dict[str, Any]] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        user_message = str(turn.get("user_message", ""))
        user_messages.append(user_message)

        message_lc = user_message.lower()
        raw_turn_index = turn.get("turn_index")
        turn_index = _normalize_turn_index(raw_turn_index, fallback=len(turn_snapshots) + 1)
        if "?" in user_message:
            has_question = True
        if "evidence" in message_lc or "study" in message_lc:
            has_evidence_keyword = True
        if (
            "next step" in message_lc
            or "follow up" in message_lc
            or "follow-up" in message_lc
            or "followup" in message_lc
        ):
            has_next_step_keyword = True

        raw_events = turn.get("director_events", [])
        if not isinstance(raw_events, list):
            raw_events = []
        director_events = [str(event) for event in raw_events if _clean_text(event, max_length=64)]
        turn_snapshots.append(
            {
                "turn_index": turn_index,
                "user_message": user_message,
                "message_lc": message_lc,
                "director_events": director_events,
                "director_phase": str(turn.get("director_phase", "unknown")),
            }
        )
        for event in raw_events:
            if event == "opening_overlong":
                opening_overlong_count += 1
            elif event == "low_information_turn":
                low_info_count += 1
            elif event == "evidence_not_addressed":
                evidence_not_addressed_count += 1
            elif event == "opening_missing_permission":
                opening_missing_permission_count += 1
            elif event == "weak_profiling_signal":
                weak_profiling_count += 1
            if event == "carryover_opening_gap":
                carryover_opening_gap = True
            if event == "carryover_profiling_gap":
                carryover_profiling_gap = True
            if event == "carryover_evidence_gap":
                carryover_evidence_gap = True
            if event == "carryover_closing_gap":
                carryover_closing_gap = True

    return {
        "opening_overlong_count": opening_overlong_count,
        "low_info_count": low_info_count,
        "evidence_not_addressed_count": evidence_not_addressed_count,
        "opening_missing_permission_count": opening_missing_permission_count,
        "weak_profiling_count": weak_profiling_count,
        "has_question": has_question,
        "has_evidence_keyword": has_evidence_keyword,
        "has_next_step_keyword": has_next_step_keyword,
        "carryover_opening_gap": carryover_opening_gap,
        "carryover_profiling_gap": carryover_profiling_gap,
        "carryover_evidence_gap": carryover_evidence_gap,
        "carryover_closing_gap": carryover_closing_gap,
        "user_messages": user_messages,
        "turns": turn_snapshots,
    }


def _score_subskills(
    *,
    subskill_ids: list[str],
    focus_subskills: set[str],
    turn_count: int,
    finish_reason: str,
    features: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    base = 2 + min(2, turn_count // 2)

    opening_overlong_count = int(features.get("opening_overlong_count", 0))
    low_info_count = int(features.get("low_info_count", 0))
    evidence_not_addressed_count = int(features.get("evidence_not_addressed_count", 0))
    has_question = bool(features.get("has_question", False))
    has_evidence_keyword = bool(features.get("has_evidence_keyword", False))
    has_next_step_keyword = bool(features.get("has_next_step_keyword", False))
    carryover_opening_gap = bool(features.get("carryover_opening_gap", False))
    carryover_profiling_gap = bool(features.get("carryover_profiling_gap", False))
    carryover_evidence_gap = bool(features.get("carryover_evidence_gap", False))
    carryover_closing_gap = bool(features.get("carryover_closing_gap", False))

    def calc_score(subskill_id: str) -> int:
        score = base + (1 if subskill_id in focus_subskills else 0)

        if subskill_id == "preparation":
            score += 1 if turn_count > 0 else 0
            score -= low_info_count
        elif subskill_id == "opening":
            score -= opening_overlong_count
            score -= features.get("opening_missing_permission_count", 0)
            score += 1 if turn_count > 0 else 0
            if carryover_opening_gap:
                score -= 1
        elif subskill_id == "profiling":
            score += 1 if has_question else 0
            score -= features.get("weak_profiling_count", 0)
            if carryover_profiling_gap:
                score -= 1
        elif subskill_id == "scientific_delivery":
            score += 1 if has_evidence_keyword else 0
            score -= evidence_not_addressed_count
            if carryover_evidence_gap:
                score -= 1
        elif subskill_id == "need_discovery":
            score += 1 if has_question else 0
            score -= low_info_count
        elif subskill_id == "objection_handling":
            score += 1 if has_evidence_keyword else 0
            score -= evidence_not_addressed_count
        elif subskill_id == "closing_followup":
            score += 1 if has_next_step_keyword else 0
            if finish_reason == "manual_finish" and not has_next_step_keyword:
                score -= 1
            if carryover_closing_gap:
                score -= 1

        return _clamp_int(score, 0, 5)

    output: dict[str, dict[str, Any]] = {}
    for subskill_id in subskill_ids:
        score = calc_score(subskill_id)
        evidence = [
            f"Derived from {turn_count} turn(s) with rule-based evaluation core.",
        ]
        output[subskill_id] = {"score": score, "evidence": evidence}
    return output


def _normalize_subskills(
    *,
    subskill_ids: list[str],
    subskills_payload: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for subskill_id in subskill_ids:
        raw = subskills_payload.get(subskill_id, {})
        if not isinstance(raw, dict):
            raw = {}
        raw_score = raw.get("score", 0)
        score = _clamp_int(int(raw_score) if isinstance(raw_score, (int, float)) else 0, 0, 5)
        evidence = _normalize_evidence_list(raw.get("evidence", []))
        if not evidence:
            evidence = ["No evidence provided."]
        normalized[subskill_id] = {"score": score, "evidence": evidence}
    return normalized


def _top_strengths(subskills: dict[str, dict[str, Any]], max_items: int = 3) -> list[str]:
    ordered = sorted(
        subskills.keys(),
        key=lambda key: (-int(subskills[key].get("score", 0)), key),
    )
    strengths = [key for key in ordered if int(subskills[key].get("score", 0)) >= 4]
    return strengths[:max_items]


def _priority_subskills(subskills: dict[str, dict[str, Any]], max_items: int = 3) -> list[str]:
    ordered = sorted(
        subskills.keys(),
        key=lambda key: (int(subskills[key].get("score", 0)), key),
    )
    priorities = [key for key in ordered if int(subskills[key].get("score", 0)) <= 2]
    if priorities:
        return priorities[:max_items]
    return ordered[:max_items]


def _build_score_contract_from_subskills(
    *,
    subskills: dict[str, dict[str, Any]],
    subskill_weights: dict[str, float],
    skill_model: dict[str, Any],
) -> dict[str, Any]:
    weighted = sum(
        float(subskills[subskill_id]["score"]) * float(subskill_weights[subskill_id])
        for subskill_id in subskill_weights
    )
    overall_score = _clamp_int(round((weighted / 5) * 100), 0, 100)
    return {
        "rubric_version": int(skill_model.get("version", 1)),
        "subskills": subskills,
        "overall_score": overall_score,
        "overall_band": _overall_band(overall_score, skill_model),
        "strengths": _top_strengths(subskills),
        "priority_subskills": _priority_subskills(subskills),
    }


def _build_compliance_flags(
    turns: list[dict[str, Any]],
    compliance_rules: dict[str, Any],
) -> list[dict[str, Any]]:
    rules_raw = compliance_rules.get("rules", []) if isinstance(compliance_rules, dict) else []
    if not isinstance(rules_raw, list):
        rules_raw = []

    user_messages = [str(t.get("user_message", "")) for t in turns]
    lower_messages = [message.lower() for message in user_messages]
    merged = "\n".join(lower_messages)

    def has_any(*keywords: str) -> bool:
        return any(keyword in merged for keyword in keywords)

    def find_evidence_turns(rule_id: str) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for i, turn in enumerate(turns):
            msg = str(turn.get("user_message", "")).lower()
            match = False
            if rule_id == "unsupported_outcome_promise":
                match = any(k in msg for k in ["guarantee", "100%", "certain outcome"])
            elif rule_id == "off_label_or_unapproved_indication":
                match = any(k in msg for k in ["off-label", "outside indication", "unapproved indication"])
            elif rule_id == "unsubstantiated_competitor_comparison":
                match = "competitor" in msg and any(k in msg for k in ["worse", "inferior", "bad"])
            elif rule_id == "adverse_event_reporting_failure":
                match = "adverse event" in msg
            elif rule_id == "fair_balance_omission":
                match = any(k in msg for k in ["benefit", "efficacy", "improve", "superior"])

            if match:
                evidence.append(
                    _structured_evidence(
                        turn=turn,
                        summary=f"Detected signal for {rule_id}.",
                        tags=["compliance", rule_id],
                    )
                )
        return evidence[:MAX_EVIDENCE_ITEMS]

    def matched(rule_id: str) -> bool:
        # Check for matching director events first (higher confidence)
        all_events = set()
        for t in turns:
            all_events.update(t.get("director_events", []))
            
        if rule_id == "adverse_event_reporting_failure":
            if "safety_reporting_not_started" in all_events or "followup_process_not_stated" in all_events:
                return True
            has_ae = has_any("adverse event", "side effect", "reaction", "unexpected effect")
            has_reporting = has_any("report", "sop", "escalat", "follow-up", "follow up", "safety dept", "safety team")
            return has_ae and not has_reporting
            
        if rule_id == "unsupported_outcome_promise":
            return has_any("guarantee", "guaranteed", "100%", "certain outcome", "always works", "no side effects")
            
        if rule_id == "off_label_or_unapproved_indication":
            return has_any("off-label", "outside indication", "unapproved indication", "not yet approved")
            
        if rule_id == "unsubstantiated_competitor_comparison":
            has_comp = has_any("competitor", "other company", "competing drug")
            has_negative = has_any("worse", "inferior", "bad", "dangerous", "unstable", "old fashioned")
            return has_comp and has_negative
            
        if rule_id == "fair_balance_omission":
            has_benefit = has_any("benefit", "efficacy", "improve", "superior", "best", "leading")
            has_risk = has_any("risk", "limitation", "uncertainty", "side effect", "adverse", "caution", "warning")
            return has_benefit and not has_risk
            
        return False

    flags: list[dict[str, Any]] = []
    
    # Check for positive compliance highlights
    has_ae_signal = has_any("adverse event", "side effect", "reaction")
    has_escalation_signal = has_any("report", "sop", "escalat", "safety team", "safety department")
    if has_ae_signal and has_escalation_signal:
        ae_turn = next((t for t in turns if any(k in str(t.get("user_message", "")).lower() for k in ["adverse event", "side effect", "reaction"])), None)
        if ae_turn:
            flags.append({
                "rule_id": "correct_ae_handling",
                "tag": "safe_ae_reporting",
                "severity": "positive",
                "summary": "Correctly identified a potential safety signal and stated the required reporting/escalation process.",
                "related_diagnosis_types": [],
                "evidence": [_structured_evidence(turn=ae_turn, summary="Learner acknowledges safety signal and states escalation process.", tags=["compliance", "positive"])],
                "required_handling": "Continue following standard SOP for all safety signals.",
                "remedial_priority": 0
            })

    for rule in rules_raw:
        if not isinstance(rule, dict):
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str):
            continue
        if not matched(rule_id):
            continue
            
        severity = rule.get("severity", "medium")
        remedial_priority = {"critical": 90, "high": 70, "medium": 40, "low": 10}.get(severity, 0)
        
        # Avoid duplicate AE flags if we already have a positive one (though matched() logic should prevent this)
        if rule_id == "adverse_event_reporting_failure" and any(f["rule_id"] == "correct_ae_handling" for f in flags):
            continue

        flags.append(
            {
                "rule_id": rule_id,
                "tag": rule.get("tag", rule_id),
                "severity": severity,
                "summary": rule.get("summary", ""),
                "related_diagnosis_types": rule.get("related_diagnosis_types", []),
                "evidence": find_evidence_turns(rule_id),
                "required_handling": rule.get("required_response", ["Follow standard compliance guidelines."])[0],
                "remedial_priority": remedial_priority
            }
        )

    include_top = (
        int(compliance_rules.get("review_policy", {}).get("include_top_flags_in_review", 3))
        if isinstance(compliance_rules, dict)
        else 3
    )
    sorted_flags = sorted(
        flags,
        key=lambda item: (
            -SEVERITY_ORDER.get(str(item.get("severity", "low")), 0) if item.get("severity") != "positive" else 100,
            str(item.get("rule_id", "")),
        ),
    )
    return sorted_flags[:max(1, include_top)]


def _apply_compliance_band_guard(
    *,
    score_contract: dict[str, Any],
    compliance_flags: list[dict[str, Any]],
    compliance_rules: dict[str, Any],
) -> dict[str, Any]:
    output = dict(score_contract)
    
    # Critical risk caps the band to critical_gap
    if any(str(flag.get("severity", "")) == "critical" for flag in compliance_flags):
        output["overall_band"] = "critical_gap"
        output["overall_score"] = min(int(output.get("overall_score", 0)), 39)
        return output
        
    # High risk caps the band to functional
    if any(str(flag.get("severity", "")) == "high" for flag in compliance_flags):
        current_band = output.get("overall_band", "unknown")
        if current_band in {"excellent", "strong"}:
            output["overall_band"] = "functional"
            output["overall_score"] = min(int(output.get("overall_score", 0)), 74)
        return output

    blocks_excellent = (
        compliance_rules.get("review_policy", {}).get("blocks_excellent_band_on", [])
        if isinstance(compliance_rules, dict)
        else []
    )
    if output.get("overall_band") == "excellent" and isinstance(blocks_excellent, list):
        blocked = {str(level) for level in blocks_excellent}
        if any(str(flag.get("severity", "")) in blocked for flag in compliance_flags):
            output["overall_band"] = "strong"
            output["overall_score"] = min(int(output.get("overall_score", 0)), 89)
    return output


def _diagnosis_catalog(diagnosis_types: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    raw_items = diagnosis_types.get("diagnosis_types", []) if isinstance(diagnosis_types, dict) else []
    if not isinstance(raw_items, list):
        return output
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        diagnosis_id = item.get("id")
        if isinstance(diagnosis_id, str):
            output[diagnosis_id] = item
    return output


def _build_diagnosis(
    *,
    subskills: dict[str, dict[str, Any]],
    features: dict[str, Any],
    diagnosis_types: dict[str, Any],
    compliance_flags: list[dict[str, Any]],
) -> dict[str, Any]:
    catalog = _diagnosis_catalog(diagnosis_types)
    selection_rules = diagnosis_types.get("selection_rules", {}) if isinstance(diagnosis_types, dict) else {}
    max_primary = int(selection_rules.get("max_primary_diagnoses", 3))

    mapping = {
        "opening": "opening_not_permission_based",
        "preparation": "insufficient_context_profiling",
        "profiling": "insufficient_context_profiling",
        "scientific_delivery": "unclear_scientific_delivery",
        "need_discovery": "insufficient_need_discovery",
        "objection_handling": "objection_response_gap",
        "closing_followup": "weak_close_or_followup",
    }

    selected: list[str] = []
    for subskill_id, payload in sorted(
        subskills.items(), key=lambda item: (int(item[1].get("score", 0)), item[0])
    ):
        score = int(payload.get("score", 0))
        if score > 2:
            continue
        diagnosis_id = mapping.get(subskill_id)
        if diagnosis_id and diagnosis_id in catalog and diagnosis_id not in selected:
            selected.append(diagnosis_id)

    if int(features.get("opening_overlong_count", 0)) > 0 and "poor_time_management" in catalog:
        if "poor_time_management" not in selected:
            selected.append("poor_time_management")

    for flag in compliance_flags:
        related = flag.get("related_diagnosis_types", [])
        if not isinstance(related, list):
            continue
        for diagnosis_id in related:
            if isinstance(diagnosis_id, str) and diagnosis_id in catalog and diagnosis_id not in selected:
                selected.append(diagnosis_id)

    selected = selected[:max(1, max_primary)]

    primary = []
    for diagnosis_id in selected:
        entry = catalog.get(diagnosis_id, {})
        primary.append(
            {
                "id": diagnosis_id,
                "kind": entry.get("kind", "skill_gap"),
                "severity": entry.get("default_severity", "medium"),
                "summary": entry.get("summary", ""),
                "related_subskills": entry.get("related_subskills", []),
                "recommendation_focus": entry.get("recommendation_focus", []),
            }
        )

    return {
        "primary": primary,
        "selection_basis": "rule_based_alpha_v1",
    }


def _score_continuity(
    *,
    subskills: dict[str, dict[str, Any]],
    continuity_context: dict[str, Any],
) -> int:
    carryover = continuity_context.get("carryover_focus_subskills", [])
    if not carryover:
        return 100

    score = 100
    for subskill_id in carryover:
        subskill_data = subskills.get(subskill_id, {})
        current_score = int(subskill_data.get("score", 0))
        if current_score <= 2:
            score -= 25
        elif current_score >= 4:
            score += 5
    return _clamp_int(score, 0, 100)


def _continuity_highlights(
    *,
    subskills: dict[str, dict[str, Any]],
    continuity_context: dict[str, Any],
    achievement: dict[str, Any] | None = None,
) -> list[str]:
    if achievement and achievement.get("status") == "achieved":
        return [f"Excellent! You successfully achieved your teaching plan targets."]

    carryover = continuity_context.get("carryover_focus_subskills", [])
    if not carryover:
        return ["No specific carryover tasks for this session."]

    highlights = []
    for subskill_id in carryover:
        subskill_data = subskills.get(subskill_id, {})
        current_score = int(subskill_data.get("score", 0))
        if current_score >= 4:
            highlights.append(f"Successfully addressed carryover weakness in {subskill_id}.")
        elif current_score <= 2:
            highlights.append(f"Carryover task {subskill_id} still requires significant focus.")
        else:
            highlights.append(f"Showing gradual improvement in carryover task {subskill_id}.")
    return highlights[:3]


def _evaluate_teaching_plan(
    *,
    subskills: dict[str, dict[str, Any]],
    teaching_plan: dict[str, Any] | None,
    scenario_focus_subskills: list[str] | None = None,
) -> dict[str, Any]:
    if not teaching_plan or not isinstance(teaching_plan, dict):
        return {"status": "no_plan"}

    focus = teaching_plan.get("focus_subskills", [])
    threshold = float(teaching_plan.get("score_threshold", 4.0))

    if not focus or not isinstance(focus, list):
        return {"status": "no_plan"}

    observable_set = set(scenario_focus_subskills) if scenario_focus_subskills else set()
    observable_focus = [s for s in focus if s in observable_set] if observable_set else focus

    if observable_set and not observable_focus:
        return {
            "status": "not_observable",
            "achieved_count": 0,
            "total_count": len(focus),
            "threshold": threshold,
        }

    achieved_count = 0
    for subskill_id in focus:
        score = float(subskills.get(subskill_id, {}).get("score", 0.0))
        if score >= threshold:
            achieved_count += 1

    if achieved_count == len(focus):
        status = "achieved"
    elif achieved_count > 0:
        status = "partially_achieved"
    else:
        status = "not_achieved"

    return {
        "status": status,
        "achieved_count": achieved_count,
        "total_count": len(focus),
        "threshold": threshold,
    }


def _build_coaching_feedback(
    *,
    priority_subskills: list[str],
    compliance_flags: list[dict[str, Any]],
) -> dict[str, Any]:
    actions: list[str] = []
    for subskill in priority_subskills[:3]:
        if subskill == "opening":
            actions.append("Open with permission and a concise relevance statement in the first turn.")
        elif subskill == "profiling":
            actions.append("Ask one targeted context question before delivering product detail.")
        elif subskill == "scientific_delivery":
            actions.append("Use one evidence-backed claim with explicit limitation framing.")
        elif subskill == "need_discovery":
            actions.append("Confirm one unmet need before moving into value delivery.")
        elif subskill == "objection_handling":
            actions.append("Acknowledge objections first, then answer with specific supporting evidence.")
        elif subskill == "closing_followup":
            actions.append("Close with one realistic next step and explicit follow-up path.")
        else:
            actions.append("Tighten the visit structure with a clear objective and message flow.")

    if any(str(flag.get("severity", "low")) in {"high", "critical"} for flag in compliance_flags):
        critical_flag = next((f for f in compliance_flags if str(f.get("severity")) in {"high", "critical"}), None)
        if critical_flag:
            summary = str(critical_flag.get("summary", "Compliance risk detected."))
            handling = str(critical_flag.get("required_handling", "Review compliance guidelines."))
            actions.insert(0, f"URGENT: {summary} -> {handling}")
        else:
            actions.insert(0, "Prioritize compliance-safe wording before persuasion in the next practice run.")

    return {
        "version": 1,
        "focus_subskills": priority_subskills[:3],
        "next_actions": actions[:4],
    }


def _build_timeline(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline = []
    for turn in turns:
        events = turn.get("director_events", [])
        phase = turn.get("director_phase", "unknown")
        
        # Heuristic rating
        is_critical_compliance = any("safety_reporting_not_started" in str(e) or "compliance_risk" in str(e) for e in events)
        is_carryover_gap = any("carryover_" in str(e) for e in events)
        if is_critical_compliance or is_carryover_gap or any(e in events for e in ["opening_missing_permission", "evidence_not_addressed"]):
            rating = "poor"
            if is_carryover_gap:
                comment = "Persistent weakness from previous sessions. Requires immediate attention."
            else:
                comment = "Significant gap in this turn. See details."
        elif any(e in events for e in ["opening_overlong", "low_information_turn", "weak_profiling_signal"]):
            rating = "fair"
        elif not events:
            rating = "excellent"
        else:
            rating = "good"
            
        # Basic comment
        if rating == "excellent":
            comment = "Solid performance. Concise and relevant."
        elif rating == "poor":
            comment = f"Significant gap in {phase}. Requires focus."
        else:
            comment = f"Functional {phase}, but could be tighter."
            
        timeline.append({
            "turn_index": int(turn.get("turn_index", 0)),
            "phase": phase,
            "rating": rating,
            "comment": comment,
            "events": events
        })
    return timeline


def _build_rule_bundle(
    *,
    inputs: ReviewBuildInputs,
    subskill_ids: list[str],
    focus_set: set[str],
    features: dict[str, Any],
) -> dict[str, Any]:
    subskills = _score_subskills(
        subskill_ids=subskill_ids,
        focus_subskills=focus_set,
        turn_count=inputs.turn_count,
        finish_reason=inputs.finish_reason,
        features=features,
    )

    compliance_flags = _build_compliance_flags(inputs.turns, inputs.compliance_rules)
    score_contract = _build_score_contract_from_subskills(
        subskills=subskills,
        subskill_weights=inputs.subskill_weights,
        skill_model=inputs.skill_model,
    )
    score_contract = _apply_compliance_band_guard(
        score_contract=score_contract,
        compliance_flags=compliance_flags,
        compliance_rules=inputs.compliance_rules,
    )
    diagnosis = _build_diagnosis(
        subskills=subskills,
        features=features,
        diagnosis_types=inputs.diagnosis_types,
        compliance_flags=compliance_flags,
    )
    coaching_feedback = _build_coaching_feedback(
        priority_subskills=score_contract["priority_subskills"],
        compliance_flags=compliance_flags,
    )
    timeline = _build_timeline(features["turns"])

    continuity_context = inputs.continuity_context or {}
    continuity_score = _score_continuity(
        subskills=subskills,
        continuity_context=continuity_context,
    )
    continuity_highlights = _continuity_highlights(
        subskills=subskills,
        continuity_context=continuity_context,
    )

    achievement = _evaluate_teaching_plan(
        subskills=subskills,
        teaching_plan=continuity_context.get("teaching_plan"),
        scenario_focus_subskills=inputs.scenario_focus_subskills,
    )
    if achievement.get("status") != "no_plan":
        continuity_highlights = _continuity_highlights(
            subskills=subskills,
            continuity_context=continuity_context,
            achievement=achievement,
        )

    # Adjust overall score with continuity weight only if carryover subskills were specified
    weighted_skill = int(score_contract["overall_score"])
    carryover = continuity_context.get("carryover_focus_subskills", [])
    if carryover:
        final_overall = _clamp_int(round(weighted_skill * 0.8 + continuity_score * 0.2), 0, 100)
    else:
        final_overall = weighted_skill
        
    score_contract["overall_score"] = final_overall
    score_contract["overall_band"] = _overall_band(final_overall, inputs.skill_model)

    _validate_schema(schema=inputs.score_schema, payload=score_contract, label="Score contract")
    _validate_schema(
        schema=inputs.judge_review_schema,
        payload={**score_contract, "diagnosis": diagnosis, "timeline": timeline},
        label="Judge output",
    )
    _validate_schema(
        schema=inputs.coach_feedback_schema,
        payload=coaching_feedback,
        label="Coach output",
    )
    _validate_schema(
        schema=inputs.compliance_flags_schema,
        payload=compliance_flags,
        label="Compliance output",
    )

    return {
        "score_contract": score_contract,
        "diagnosis": diagnosis,
        "coaching_feedback": coaching_feedback,
        "compliance_flags": compliance_flags,
        "timeline": timeline,
        "continuity_channel": {
            "score": continuity_score,
            "highlights": continuity_highlights,
            "carryover_subskills": continuity_context.get("carryover_focus_subskills", []),
            "teaching_plan_achievement": achievement,
        },
    }


def _as_model_artifacts(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    return None


def build_review_payload(inputs: ReviewBuildInputs) -> dict[str, Any]:
    subskill_ids = list(inputs.subskill_weights.keys())
    focus_set = set(inputs.scenario_focus_subskills)
    features = _collect_turn_features(inputs.turns)

    rule_bundle = _build_rule_bundle(
        inputs=inputs,
        subskill_ids=subskill_ids,
        focus_set=focus_set,
        features=features,
    )

    selected_score_contract = dict(rule_bundle["score_contract"])
    selected_diagnosis = dict(rule_bundle["diagnosis"])
    selected_coaching_feedback = dict(rule_bundle["coaching_feedback"])
    selected_compliance_flags = list(rule_bundle["compliance_flags"])

    artifact_sources = {
        "judge": "rule",
        "coach": "rule",
        "compliance": "rule",
    }
    artifact_modes = {
        "judge": "rule",
        "coach": "rule",
        "compliance": "rule",
    }
    fallback_reasons: list[str] = []

    if inputs.model_error:
        fallback_reasons.append(f"model_generator_error: {inputs.model_error}")

    model_artifacts = _as_model_artifacts(inputs.model_artifacts)
    if inputs.model_artifacts is not None and model_artifacts is None:
        fallback_reasons.append("model_artifacts_non_object")

    model_meta: dict[str, Any] = dict(inputs.model_meta) if isinstance(inputs.model_meta, dict) else {}
    generated_artifact_mode = "model"
    raw_generator = model_meta.get("generator")
    if isinstance(raw_generator, str) and raw_generator.strip().lower() == "mock":
        generated_artifact_mode = "mock"

    if model_artifacts is not None:
        raw_meta = model_artifacts.get("model_meta")
        if isinstance(raw_meta, dict):
            model_meta.update(raw_meta)
            raw_generator = model_meta.get("generator")
            if isinstance(raw_generator, str) and raw_generator.strip().lower() == "mock":
                generated_artifact_mode = "mock"
            else:
                generated_artifact_mode = "model"

        model_compliance = model_artifacts.get("compliance_flags")
        if model_compliance is None:
            fallback_reasons.append("model_compliance_missing")
        else:
            try:
                _validate_schema(
                    schema=inputs.compliance_flags_schema,
                    payload=model_compliance,
                    label="Compliance output",
                )
                selected_compliance_flags = list(model_compliance)
                artifact_sources["compliance"] = "model"
                artifact_modes["compliance"] = generated_artifact_mode
            except Exception as exc:
                fallback_reasons.append(f"model_compliance_failed: {exc}")

        model_judge = model_artifacts.get("judge_review")
        if model_judge is None:
            fallback_reasons.append("model_judge_missing")
        else:
            try:
                if not isinstance(model_judge, dict):
                    raise ValueError("judge_review must be an object")
                _validate_schema(
                    schema=inputs.judge_review_schema,
                    payload=model_judge,
                    label="Judge output",
                )

                model_subskills_payload = model_judge.get("subskills")
                if not isinstance(model_subskills_payload, dict):
                    raise ValueError("judge_review.subskills must be an object")

                normalized_subskills = _normalize_subskills(
                    subskill_ids=subskill_ids,
                    subskills_payload=model_subskills_payload,
                )
                model_score_contract = _build_score_contract_from_subskills(
                    subskills=normalized_subskills,
                    subskill_weights=inputs.subskill_weights,
                    skill_model=inputs.skill_model,
                )
                model_score_contract = _apply_compliance_band_guard(
                    score_contract=model_score_contract,
                    compliance_flags=selected_compliance_flags,
                    compliance_rules=inputs.compliance_rules,
                )

                model_diagnosis = model_judge.get("diagnosis")
                if not isinstance(model_diagnosis, dict):
                    raise ValueError("judge_review.diagnosis must be an object")

                _validate_schema(
                    schema=inputs.score_schema,
                    payload=model_score_contract,
                    label="Score contract",
                )
                _validate_schema(
                    schema=inputs.judge_review_schema,
                    payload={**model_score_contract, "diagnosis": model_diagnosis, "timeline": timeline},
                    label="Judge output",
                )

                selected_score_contract = model_score_contract
                selected_diagnosis = model_diagnosis
                artifact_sources["judge"] = "model"
                artifact_modes["judge"] = generated_artifact_mode
            except Exception as exc:
                fallback_reasons.append(f"model_judge_failed: {exc}")

        model_coach = model_artifacts.get("coaching_feedback")
        if model_coach is None:
            fallback_reasons.append("model_coach_missing")
        else:
            try:
                _validate_schema(
                    schema=inputs.coach_feedback_schema,
                    payload=model_coach,
                    label="Coach output",
                )
                selected_coaching_feedback = dict(model_coach)
                artifact_sources["coach"] = "model"
                artifact_modes["coach"] = generated_artifact_mode
            except Exception as exc:
                fallback_reasons.append(f"model_coach_failed: {exc}")

    linked_subskills = _link_subskill_evidence_to_turns(
        subskills=selected_score_contract["subskills"],
        turn_features=features,
    )
    selected_score_contract = {
        **selected_score_contract,
        "subskills": linked_subskills,
    }

    _validate_schema(
        schema=inputs.score_schema,
        payload=selected_score_contract,
        label="Score contract",
    )
    _validate_schema(
        schema=inputs.judge_review_schema,
        payload={**selected_score_contract, "diagnosis": selected_diagnosis, "timeline": rule_bundle["timeline"]},
        label="Judge output",
    )

    return {
        **selected_score_contract,
        "diagnosis": selected_diagnosis,
        "timeline": rule_bundle["timeline"],
        "coaching_feedback": selected_coaching_feedback,
        "compliance_flags": selected_compliance_flags,
        "compliance_channel": {
            "flags": selected_compliance_flags,
            "overall_status": "at_risk" if any(f.get("severity") in {"high", "critical"} for f in selected_compliance_flags) else "compliant",
            "remedial_required": any(f.get("remedial_priority", 0) > 50 for f in selected_compliance_flags)
        },
        "continuity_channel": rule_bundle["continuity_channel"],
        "benchmarking_channel": get_peer_benchmark(inputs.scenario_id or "unknown"),
        "meta": {
            "finish_reason": inputs.finish_reason,
            "turn_count": inputs.turn_count,
            "evaluation_mode": "evaluation_core_v1",
            "artifact_sources": artifact_sources,
            "artifact_modes": artifact_modes,
            "fallback_reasons": fallback_reasons,
            "model_meta": model_meta,
            "prompting": inputs.prompting_meta or {},
        },
    }

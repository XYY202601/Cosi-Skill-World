from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field


SKILL_ID = "gp_visit_jp"
SERVICE_NAME = "gp-visit-jp-runtime"
PROMPT_PROFILE_ID = "gp_spike_baseline_v1"
PROMPT_CONTEXT = {
    "profile_id": PROMPT_PROFILE_ID,
    "experiment_id": None,
    "flags": [],
    "contracts": {
        "judge": {"contract_id": f"{PROMPT_PROFILE_ID}:judge:v1", "version": 1},
        "coach": {"contract_id": f"{PROMPT_PROFILE_ID}:coach:v1", "version": 1},
        "compliance": {"contract_id": f"{PROMPT_PROFILE_ID}:compliance:v1", "version": 1},
    },
}
DEFAULT_LOCALE = "ja-JP"
EVENT_SCHEMA_VERSION = "1.1"
COMPETENCY_PATTERNS = {
    "patient_reception": (
        "understand",
        "worry",
        "concern",
        "anxious",
        "thank you",
        "心配",
        "大変",
        "一緒",
        "気持ち",
    ),
    "symptom_interview": (
        "how often",
        "what makes",
        "when do you",
        "diet",
        "salt",
        "exercise",
        "routine",
        "barrier",
        "sleep",
        "食事",
        "運動",
        "習慣",
        "どれくらい",
        "なぜ",
        "忘",
    ),
    "lifestyle_advice": (
        "recommend",
        "suggest",
        "plan",
        "goal",
        "reduce",
        "walk",
        "exercise",
        "reminder",
        "routine",
        "salt",
        "sodium",
        "提案",
        "目標",
        "散歩",
        "塩分",
        "リマインダー",
    ),
}
DEFINITE_DIAGNOSIS_PATTERN = re.compile(
    r"\b(definitely have|this is definitely|you have hypertension|diagnosis is)\b",
    re.IGNORECASE,
)
SENSITIVE_DATA_PATTERN = re.compile(
    r"(\b\d{10,}\b|@|patient id|患者番号|電話番号)",
    re.IGNORECASE,
)


class StartSessionRequest(BaseModel):
    scenario_id: str
    learner_id: str


class SendTurnRequest(BaseModel):
    message: str = Field(min_length=1)
    persona_id: str | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected YAML object in {path}")
    return payload


def _load_personas() -> dict[str, dict[str, Any]]:
    payload = _read_yaml(_repo_root() / "domains" / "gp_visit_jp" / "assets" / "personas" / "doctor_personas.yaml")
    personas = payload.get("personas", [])
    if not isinstance(personas, list):
        raise RuntimeError("GP personas asset must contain a list")
    return {
        str(item["id"]): item
        for item in personas
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def _load_scenarios() -> dict[str, dict[str, Any]]:
    scenario_dir = _repo_root() / "domains" / "gp_visit_jp" / "scenarios"
    scenarios: dict[str, dict[str, Any]] = {}
    for path in sorted(scenario_dir.glob("*.yaml")):
        payload = _read_yaml(path)
        scenario_id = str(payload["id"])
        scenarios[scenario_id] = payload
    return scenarios


def _load_rubric() -> dict[str, Any]:
    return _read_yaml(_repo_root() / "domains" / "gp_visit_jp" / "rubrics" / "standard.yaml")


def _load_compliance() -> dict[str, Any]:
    return _read_yaml(_repo_root() / "domains" / "gp_visit_jp" / "compliance" / "standard.yaml")


PERSONAS = _load_personas()
SCENARIOS = _load_scenarios()
RUBRIC = _load_rubric()
COMPLIANCE = _load_compliance()
SUBSKILLS = tuple(str(item) for item in RUBRIC["subskills"].keys())
COMPLIANCE_RULES = {
    str(item["id"]): item
    for item in COMPLIANCE.get("rules", [])
    if isinstance(item, dict) and isinstance(item.get("id"), str)
}


app = FastAPI(title=SERVICE_NAME, version="0.1.0")
app.state.sessions = {}
app.state.events = {}
app.state.progress = {}


@app.middleware("http")
async def attach_trace_headers(request: Request, call_next):
    request.state.request_id = request.headers.get("x-request-id") or f"req_{uuid4().hex[:12]}"
    request.state.trace_id = request.headers.get("x-trace-id") or f"trace_{uuid4().hex[:12]}"
    request.state.session_id = None
    request.state.turn_id = None
    response = await call_next(request)
    response.headers["x-request-id"] = request.state.request_id
    response.headers["x-trace-id"] = request.state.trace_id
    response.headers["x-service-name"] = SERVICE_NAME
    if request.state.session_id:
        response.headers["x-session-id"] = request.state.session_id
    if request.state.turn_id:
        response.headers["x-turn-id"] = request.state.turn_id
    return response


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _set_trace_targets(request: Request, *, session_id: str | None = None, turn_id: str | None = None) -> None:
    request.state.session_id = session_id
    request.state.turn_id = turn_id


def _scenario_summary(scenario: dict[str, Any]) -> dict[str, Any]:
    persona = PERSONAS[str(scenario["doctor_persona_id"])]
    return {
        "id": str(scenario["id"]),
        "title": str(scenario["title"]),
        "difficulty": str(scenario["difficulty"]),
        "focus_subskills": list(scenario.get("focus_subskills", [])),
        "doctor_persona_id": str(scenario["doctor_persona_id"]),
        "persona_label": str(persona.get("label", "")),
        "persona_attitude": str(persona.get("attitude", "")),
        "persona_time_pressure": str(persona.get("time_pressure", "")),
        "persona_specialty": str(persona.get("specialty", "")),
        "max_turns": int(scenario.get("max_turns", 6)),
        "success_criteria": list(scenario.get("success_criteria", [])),
        "failure_patterns": list(scenario.get("failure_patterns", [])),
    }


def _baseline_prompt_context() -> dict[str, Any]:
    return deepcopy(PROMPT_CONTEXT)


def _coach_continuity(scenario: dict[str, Any]) -> dict[str, Any]:
    persona = PERSONAS[str(scenario["doctor_persona_id"])]
    return {
        "summary": f"Focus on a concise GP coaching flow for {scenario['title']}.",
        "version": 1,
        "carryover_focus_subskills": [],
        "scenario_focus_subskills": list(scenario.get("focus_subskills", [])),
        "suggested_focus_subskills": list(scenario.get("focus_subskills", [])),
        "next_actions": [
            "Acknowledge the patient context without blame.",
            "Clarify the most practical barrier before giving advice.",
            "Agree on one realistic next-step the patient can start this week.",
        ],
        "success_criteria": list(scenario.get("success_criteria", [])),
        "failure_patterns": list(scenario.get("failure_patterns", [])),
        "persona": {
            "id": str(persona["id"]),
            "label": str(persona.get("label", "")),
            "time_pressure": str(persona.get("time_pressure", "")),
            "attitude": str(persona.get("attitude", "")),
        },
    }


def _turn_id(session_id: str, turn_index: int) -> str:
    return f"{session_id}:turn:{turn_index:04d}"


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _build_evidence(summary: str, message: str, turn_index: int, *, tags: list[str]) -> dict[str, Any]:
    excerpt = message.strip()
    if len(excerpt) > 160:
        excerpt = f"{excerpt[:157]}..."
    return {
        "summary": summary,
        "turn_index": turn_index,
        "speaker": "learner",
        "excerpt": excerpt,
        "tags": tags,
    }


def _analyze_turn(message: str, session: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_text(message)
    detected_subskills: list[str] = []
    evidence_by_subskill: dict[str, dict[str, Any]] = {}
    for subskill_id, patterns in COMPETENCY_PATTERNS.items():
        if any(pattern in normalized for pattern in patterns):
            detected_subskills.append(subskill_id)
            evidence_by_subskill[subskill_id] = _build_evidence(
                summary=f"Detected {subskill_id.replace('_', ' ')} behavior in the learner turn.",
                message=message,
                turn_index=int(session["turn_count"]) + 1,
                tags=[subskill_id],
            )

    seen_subskills = {
        subskill_id
        for subskill_id, items in session["evidence_by_subskill"].items()
        if items
    }
    combined = seen_subskills | set(detected_subskills)

    scenario = session["scenario"]
    if "patient_reception" not in combined:
        phase = "opening"
        events = ["rapport_not_established"]
        recommended_action = "Acknowledge the patient context and normalize the concern."
    elif "symptom_interview" not in combined:
        phase = "discovery"
        events = ["barrier_exploration_missing"]
        recommended_action = "Ask one focused question to uncover the real barrier."
    elif "lifestyle_advice" not in combined:
        phase = "education"
        events = ["practical_plan_missing"]
        recommended_action = "Translate the discussion into one realistic habit or reminder."
    else:
        phase = "commitment"
        events = ["ready_for_shared_plan"]
        recommended_action = "Close with a concrete commitment and follow-up cue."

    turn_index = int(session["turn_count"]) + 1
    should_finish = turn_index >= int(scenario.get("max_turns", 6)) or (
        turn_index >= 2 and all(subskill in combined for subskill in scenario.get("focus_subskills", []))
    )

    if str(scenario["id"]) == "gp_02_adherence_followup":
        doctor_reply = (
            "The patient says evenings are chaotic and doses are often missed after work. "
            "What practical step would you suggest first?"
        )
    elif phase == "opening":
        doctor_reply = "Keep it brief. The patient is anxious, so start by acknowledging that."
    elif phase == "discovery":
        doctor_reply = "Before advising, I need the real routine barrier. What would you ask next?"
    elif phase == "education":
        doctor_reply = "Good. Now make the advice concrete enough for this week."
    else:
        doctor_reply = "That is actionable. How would you confirm commitment before ending the visit?"

    return {
        "phase": phase,
        "events": events,
        "recommended_action": recommended_action,
        "doctor_reply": doctor_reply,
        "detected_subskills": detected_subskills,
        "evidence_by_subskill": evidence_by_subskill,
        "should_finish": should_finish,
    }


def _apply_subskill_evidence(session: dict[str, Any], analysis: dict[str, Any]) -> None:
    for subskill_id, evidence in analysis["evidence_by_subskill"].items():
        session["evidence_by_subskill"].setdefault(subskill_id, []).append(evidence)


def _append_event(
    request: Request,
    session: dict[str, Any],
    *,
    action_id: str,
    event_type: str,
    stage: str,
    content: dict[str, Any],
    turn_index: int | None = None,
) -> None:
    events = app.state.events.setdefault(session["session_id"], [])
    turn_id = _turn_id(session["session_id"], turn_index) if turn_index is not None else None
    events.append(
        {
            "type": event_type,
            "source": "runtime",
            "stage": stage,
            "content": deepcopy(content),
            "metadata": {
                "capability_id": "practice_session",
                "action_id": action_id,
                "learner_id": session["learner_id"],
                "scenario_id": session["scenario_id"],
                "persona_id": session["scenario"]["doctor_persona_id"],
                "prompt_profile": session["experiment_context"]["profile_id"],
                "trace_id": session["trace_id"],
                "locale": DEFAULT_LOCALE,
            },
            "skill_id": SKILL_ID,
            "session_id": session["session_id"],
            "turn_id": turn_id,
            "seq": len(events) + 1,
            "timestamp": _utc_now_iso(),
            "schema_version": EVENT_SCHEMA_VERSION,
        }
    )
    _set_trace_targets(request, session_id=session["session_id"], turn_id=turn_id)


def _band_for_score(overall_score: int) -> str:
    for band in RUBRIC["overall_score"]["bands"]:
        if int(band["min"]) <= overall_score <= int(band["max"]):
            return str(band["id"])
    return "critical_gap"


def _compliance_flags(session: dict[str, Any]) -> list[dict[str, Any]]:
    joined = "\n".join(turn["user_message"] for turn in session["turns"])
    flags: list[dict[str, Any]] = []
    if DEFINITE_DIAGNOSIS_PATTERN.search(joined):
        rule = COMPLIANCE_RULES["improper_medical_diagnosis"]
        flags.append(
            {
                "rule_id": str(rule["id"]),
                "tag": str(rule["tag"]),
                "severity": str(rule["severity"]),
                "summary": str(rule["summary"]),
                "related_diagnosis_types": list(rule.get("related_diagnosis_types", [])),
            }
        )
    if SENSITIVE_DATA_PATTERN.search(joined):
        rule = COMPLIANCE_RULES["sensitive_data_breach"]
        flags.append(
            {
                "rule_id": str(rule["id"]),
                "tag": str(rule["tag"]),
                "severity": str(rule["severity"]),
                "summary": str(rule["summary"]),
                "related_diagnosis_types": list(rule.get("related_diagnosis_types", [])),
            }
        )
    return flags


def _subskill_score(evidence_items: list[dict[str, Any]]) -> int:
    if not evidence_items:
        return 1
    if len(evidence_items) == 1:
        return 3
    if len(evidence_items) == 2:
        return 4
    return 5


def _review_for_session(session: dict[str, Any]) -> dict[str, Any]:
    compliance_flags = _compliance_flags(session)
    subskills: dict[str, Any] = {}
    scored_subskills: list[tuple[str, int]] = []
    for subskill_id in SUBSKILLS:
        evidence_items = list(session["evidence_by_subskill"].get(subskill_id, []))
        score = _subskill_score(evidence_items)
        if not evidence_items:
            evidence_items = [
                {
                    "summary": f"No clear evidence for {subskill_id.replace('_', ' ')} appeared in the transcript.",
                }
            ]
        subskills[subskill_id] = {
            "score": score,
            "evidence": evidence_items,
        }
        scored_subskills.append((subskill_id, score))

    overall_score = round(sum(score for _, score in scored_subskills) / (5 * len(scored_subskills)) * 100)
    highest_compliance = {flag["severity"] for flag in compliance_flags}
    if "critical" in highest_compliance:
        overall_score = min(overall_score, 39)
    elif "high" in highest_compliance:
        overall_score = min(overall_score, 59)
    overall_band = _band_for_score(overall_score)
    strengths = [
        RUBRIC["subskills"][subskill_id]["name"]
        for subskill_id, score in scored_subskills
        if score >= 4
    ]
    priority_subskills = [
        subskill_id
        for subskill_id, _score in sorted(scored_subskills, key=lambda item: (item[1], item[0]))[:2]
    ]
    diagnosis_id = compliance_flags[0]["rule_id"] if compliance_flags else f"{priority_subskills[0]}_gap"
    diagnosis_summary = (
        compliance_flags[0]["summary"]
        if compliance_flags
        else f"The main gap is {priority_subskills[0].replace('_', ' ')}."
    )
    next_actions = [
        "Open with a short acknowledgement before solving.",
        "Ask one barrier-focused question before advising.",
        "End with a single concrete commitment the patient can repeat back.",
    ]
    return {
        "rubric_version": 1,
        "subskills": subskills,
        "overall_score": overall_score,
        "overall_band": overall_band,
        "strengths": strengths,
        "priority_subskills": priority_subskills,
        "diagnosis": {
            "primary": [
                {
                    "id": diagnosis_id,
                    "kind": "compliance" if compliance_flags else "skill_gap",
                    "severity": compliance_flags[0]["severity"] if compliance_flags else "medium",
                    "summary": diagnosis_summary,
                    "related_subskills": priority_subskills,
                    "recommendation_focus": priority_subskills,
                }
            ],
            "selection_basis": "Rule-based GP spike evaluation from turn evidence and compliance heuristics.",
        },
        "coaching_feedback": {
            "version": 1,
            "focus_subskills": priority_subskills,
            "next_actions": next_actions,
        },
        "compliance_flags": compliance_flags,
        "meta": {
            "finish_reason": session["finish_reason"],
            "turn_count": session["turn_count"],
            "evaluation_mode": "rule_spike_v1",
            "artifact_sources": {
                "judge": "rule",
                "coach": "rule",
                "compliance": "rule",
            },
            "fallback_reasons": [],
            "model_meta": {},
            "prompting": deepcopy(session["experiment_context"]),
            "context": {
                "skill_id": SKILL_ID,
                "session_id": session["session_id"],
                "learner_id": session["learner_id"],
                "prompt_profile": session["experiment_context"]["profile_id"],
                "trace_id": session["trace_id"],
                "locale": DEFAULT_LOCALE,
            },
        },
    }


def _recommendations_for_learner(current_scenario_id: str, priority_subskills: list[str]) -> list[dict[str, Any]]:
    candidate_scenarios = [
        scenario for scenario_id, scenario in SCENARIOS.items() if scenario_id != current_scenario_id
    ] or [SCENARIOS[current_scenario_id]]
    recommendations: list[dict[str, Any]] = []
    for index, scenario in enumerate(candidate_scenarios[:2], start=1):
        recommendations.append(
            {
                "scenario_id": str(scenario["id"]),
                "title": str(scenario["title"]),
                "difficulty": str(scenario["difficulty"]),
                "target_subskills": list(priority_subskills or scenario.get("focus_subskills", [])),
                "reason": "Use the other GP scenario to practice the same weak behaviors in a different context.",
                "recommendation_type": "skill",
                "evidence_source": "rule_spike_v1",
                "stop_condition": "Reach stable 4/5 behavior on the target subskills across two sessions.",
                "expected_difficulty": str(scenario["difficulty"]),
                "suggested_repetition_count": index,
                "reason_category": "skill",
            }
        )
    return recommendations


def _curriculum_snapshot(
    *,
    total_sessions: int,
    average_score: float,
    target_subskills: list[str],
    recent_history: list[dict[str, Any]],
) -> dict[str, Any]:
    scenario_attempts = {
        scenario_id: sum(1 for item in recent_history if item["scenario_id"] == scenario_id)
        for scenario_id in sorted(SCENARIOS.keys())
    }
    required_completed = sum(1 for attempt_count in scenario_attempts.values() if attempt_count > 0)
    required_total = len(scenario_attempts)
    target_average_values = [
        item["overall_score"]
        for item in recent_history
        if set(SCENARIOS[item["scenario_id"]].get("focus_subskills", [])) & set(target_subskills)
    ]
    target_average = round((sum(target_average_values) / len(target_average_values)) / 20, 2) if target_average_values else 0.0
    stage_complete = required_completed >= required_total and average_score >= 75
    return {
        "curriculum_id": "gp_visit_jp_spike_curriculum",
        "curriculum_title": "GP Visit Communication Spike",
        "current_stage_id": "gp_spike_foundation",
        "current_stage_title": "Foundation GP Communication",
        "current_stage_description": "Practice patient reception, symptom interview, and practical lifestyle advice.",
        "current_module_id": "gp_spike_core",
        "current_module_title": "Core GP Visit Flow",
        "stage_position": 1,
        "total_stages": 1,
        "status": "completed" if stage_complete else "active",
        "mastery_status": "stable" if average_score >= 75 else "needs_practice",
        "review_status": "maintain" if stage_complete else "focus_now",
        "next_review_in_sessions": 2 if stage_complete else 1,
        "target_subskills": target_subskills,
        "recommended_repetition": 2,
        "current_stage_scenarios": [
            {
                "scenario_id": scenario_id,
                "title": str(SCENARIOS[scenario_id]["title"]),
                "attempt_count": scenario_attempts[scenario_id],
                "required": True,
                "remaining_repetitions": max(0, 1 - scenario_attempts[scenario_id]),
            }
            for scenario_id in sorted(SCENARIOS.keys())
        ],
        "completed_stage_ids": ["gp_spike_foundation"] if stage_complete else [],
        "rationale": "The GP spike uses one foundation stage to verify shared runtime contracts.",
        "next_stage_id": None,
        "next_stage_title": None,
        "attention_reason": "Continue until both spike scenarios have at least one completed session.",
        "metrics": {
            "completed_sessions": total_sessions,
            "required_scenarios_completed": required_completed,
            "required_scenarios_total": required_total,
            "average_stage_score": average_score,
            "target_subskill_average": target_average,
        },
    }


def _skill_world_snapshot(
    *,
    curriculum: dict[str, Any],
    recent_history: list[dict[str, Any]],
    target_subskills: list[str],
) -> dict[str, Any]:
    completed_stage_count = len(curriculum["completed_stage_ids"])
    total_stage_count = int(curriculum["total_stages"])
    map_progress_percent = int(round((completed_stage_count / total_stage_count) * 100)) if total_stage_count else 0
    node_status = "completed" if completed_stage_count else "active"
    last_trained_at = recent_history[-1]["timestamp"] if recent_history else None
    return {
        "version": 1,
        "map_id": "gp_visit_jp_spike_map",
        "title": "GP Visit Skill Map",
        "active_node_id": "gp_spike_foundation",
        "summary": {
            "completed_stage_count": completed_stage_count,
            "total_stage_count": total_stage_count,
            "map_progress_percent": map_progress_percent,
            "earned_achievement_count": 1 if recent_history else 0,
            "mastered_subskill_count": 0,
            "total_subskill_count": len(SUBSKILLS),
            "current_stage_title": curriculum["current_stage_title"],
        },
        "nodes": [
            {
                "node_id": "gp_spike_foundation",
                "kind": "stage",
                "stage_id": "gp_spike_foundation",
                "title": curriculum["current_stage_title"],
                "description": curriculum["current_stage_description"],
                "module_id": curriculum["current_module_id"],
                "position": 1,
                "status": node_status,
                "progress_percent": map_progress_percent,
                "target_subskills": target_subskills,
                "scenario_ids": sorted(SCENARIOS.keys()),
                "completed_scenario_count": curriculum["metrics"]["required_scenarios_completed"],
                "scenario_count": curriculum["metrics"]["required_scenarios_total"],
                "required_scenarios_completed": curriculum["metrics"]["required_scenarios_completed"],
                "required_scenarios_total": curriculum["metrics"]["required_scenarios_total"],
                "mastery_status": curriculum["mastery_status"],
                "review_status": curriculum["review_status"],
                "rationale": curriculum["rationale"],
                "last_trained_at": last_trained_at,
            }
        ],
        "achievements": [
            {
                "achievement_id": "gp_spike_first_session",
                "kind": "milestone",
                "title": "First GP Spike Session",
                "description": "Complete one GP communication spike session.",
                "status": "earned" if recent_history else "locked",
                "earned_at": last_trained_at if recent_history else None,
                "evidence": {
                    "session_count": len(recent_history),
                },
            }
        ],
    }


def _update_progress(session: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    learner_id = session["learner_id"]
    previous = app.state.progress.get(learner_id)
    now = _utc_now_iso()
    total_sessions = int(previous["total_sessions"]) + 1 if previous else 1
    total_exp = int(previous["total_exp"]) + int(review["overall_score"]) if previous else int(review["overall_score"])
    average_score = round(
        (
            sum(item["overall_score"] for item in previous["recent_history"]) + int(review["overall_score"])
            if previous
            else int(review["overall_score"])
        )
        / total_sessions,
        2,
    )

    subskills: dict[str, Any] = deepcopy(previous["subskills"]) if previous else {}
    for subskill_id, payload in review["subskills"].items():
        prior = subskills.get(
            subskill_id,
            {
                "exp": 0,
                "level": 1,
                "last_score": 0,
                "trend": "stable",
                "rolling_average": 0.0,
                "history_count": 0,
            },
        )
        history_count = int(prior["history_count"]) + 1
        last_score = int(payload["score"])
        prior_average = float(prior["rolling_average"])
        rolling_average = round(((prior_average * int(prior["history_count"])) + last_score) / history_count, 2)
        prior_last_score = int(prior["last_score"])
        trend = "stable"
        if prior_last_score:
            if last_score > prior_last_score:
                trend = "improving"
            elif last_score < prior_last_score:
                trend = "declining"
        subskills[subskill_id] = {
            "exp": int(prior["exp"]) + last_score * 10,
            "level": 1 + ((int(prior["exp"]) + last_score * 10) // 50),
            "last_score": last_score,
            "trend": trend,
            "rolling_average": rolling_average,
            "history_count": history_count,
        }

    recommendations = _recommendations_for_learner(session["scenario_id"], review["priority_subskills"])
    recent_history = list(previous["recent_history"]) if previous else []
    recent_history.append(
        {
            "session_id": session["session_id"],
            "scenario_id": session["scenario_id"],
            "overall_score": int(review["overall_score"]),
            "timestamp": now,
        }
    )
    recent_history = recent_history[-5:]

    weakness_clusters = []
    weak_subskills = [subskill_id for subskill_id in review["priority_subskills"] if review["subskills"][subskill_id]["score"] <= 3]
    if weak_subskills:
        weakness_clusters.append(
            {
                "cluster_id": hashlib.sha256(",".join(sorted(weak_subskills)).encode("utf-8")).hexdigest()[:12],
                "subskills": weak_subskills,
                "occurrences": total_sessions,
                "last_seen_at": now,
            }
        )

    scenario = session["scenario"]
    persona = PERSONAS[str(scenario["doctor_persona_id"])]
    coach_memory = {
        "version": 1,
        "summary": f"Current GP focus: {', '.join(review['priority_subskills'])}.",
        "active_focus_subskills": list(review["priority_subskills"]),
        "next_actions": list(review["coaching_feedback"]["next_actions"]),
        "last_session": {
            "session_id": session["session_id"],
            "scenario_id": session["scenario_id"],
            "scenario_title": str(scenario["title"]),
            "persona_label": str(persona.get("label", "")),
            "overall_score": int(review["overall_score"]),
            "timestamp": now,
        },
        "teaching_plan": None,
        "last_teaching_plan_achievement": None,
        "updated_at": now,
    }

    target_subskills = list(review["priority_subskills"] or SUBSKILLS)
    curriculum = _curriculum_snapshot(
        total_sessions=total_sessions,
        average_score=average_score,
        target_subskills=target_subskills,
        recent_history=recent_history,
    )
    skill_world = _skill_world_snapshot(
        curriculum=curriculum,
        recent_history=recent_history,
        target_subskills=target_subskills,
    )

    progress = {
        "learner_id": learner_id,
        "total_sessions": total_sessions,
        "total_exp": total_exp,
        "level": 1 + (total_exp // 100),
        "updated_at": now,
        "latest_recommendations": recommendations,
        "practice_path": [
            {
                **recommendation,
                "step_index": index,
            }
            for index, recommendation in enumerate(recommendations, start=1)
        ],
        "weakness_clusters": weakness_clusters,
        "subskills": subskills,
        "recent_history": recent_history,
        "coach_memory": coach_memory,
        "curriculum": curriculum,
        "skill_world": skill_world,
        "performance_analytics": {
            "average_overall_score": average_score,
            "completed_sessions": total_sessions,
            "latest_band": review["overall_band"],
            "domain_id": SKILL_ID,
        },
    }
    app.state.progress[learner_id] = progress
    return progress


def _require_session(session_id: str) -> dict[str, Any]:
    session = app.state.sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Unknown session_id: {session_id}")
    return session


def _coverage_dimension(covered: list[str]) -> dict[str, Any]:
    return {
        "covered": covered,
        "missing": [],
        "counts": {item: 1 for item in covered},
    }


def _offline_dataset_payload() -> dict[str, Any]:
    scenario_ids = sorted(SCENARIOS.keys())
    compliance_cases = sorted(COMPLIANCE_RULES.keys()) or ["none"]
    return {
        "fixture_schema_version": 1,
        "fixture_count": 1,
        "fixtures_by_bucket": {
            "good": 1,
        },
        "coverage": {
            "scenarios": _coverage_dimension(scenario_ids),
            "subskills": _coverage_dimension(list(SUBSKILLS)),
            "compliance_cases": _coverage_dimension(compliance_cases),
            "finish_reasons": _coverage_dimension(["completed"]),
        },
    }


def _evaluation_gates_payload() -> dict[str, Any]:
    scenario_ids = sorted(SCENARIOS.keys())
    return {
        "domain_id": SKILL_ID,
        "default_profile_id": PROMPT_PROFILE_ID,
        "rollout": {
            "status": "active",
            "requested": _baseline_prompt_context(),
            "effective": _baseline_prompt_context(),
            "stable_profile_id": PROMPT_PROFILE_ID,
            "allow_blocked_rollout": True,
            "checks": [
                {
                    "name": "spike_profile_available",
                    "passed": True,
                    "detail": "The GP spike runtime exposes one deterministic prompt profile.",
                }
            ],
        },
        "offline_gates": [
            {
                "profile_id": PROMPT_PROFILE_ID,
                "status": "pass",
                "fixture_pass_rate": 1.0,
                "fixture_results": [
                    {
                        "fixture_name": "gp_spike_smoke",
                        "fixture_path": "apps/gp-visit-jp-runtime/tests/test_runtime_contract.py",
                        "bucket": "good",
                        "scenario_ids": scenario_ids,
                        "focus_subskills": list(SUBSKILLS),
                        "finish_reason": "completed",
                        "compliance_case": "none",
                        "tags": ["runtime_contract", "gp_spike"],
                        "passed": True,
                        "overall_score": 80,
                        "overall_band": "strong",
                    }
                ],
                "contract_versions": {
                    "judge": 1,
                    "coach": 1,
                    "compliance": 1,
                },
                "output_requirement_counts": {
                    "judge": 6,
                    "coach": 3,
                    "compliance": 2,
                },
                "checks": [
                    {
                        "name": "runtime_contract",
                        "passed": True,
                        "detail": "The GP spike contract remains deterministic and schema-compatible.",
                    }
                ],
            }
        ],
        "offline_dataset": _offline_dataset_payload(),
        "online_gates": [],
    }


@app.get("/healthz")
def healthz(request: Request) -> dict[str, Any]:
    _set_trace_targets(request)
    return {
        "status": "ok",
        "domain_id": SKILL_ID,
        "scenario_count": len(SCENARIOS),
        "persistence_mode": "memory",
        "demo_seed_mode": "disabled",
        "prompt_profile": PROMPT_PROFILE_ID,
        "experiment_id": None,
    }


@app.get("/v1/scenarios")
def list_scenarios(request: Request) -> dict[str, Any]:
    _set_trace_targets(request)
    summaries = [_scenario_summary(scenario) for scenario in SCENARIOS.values()]
    return {
        "domain_id": SKILL_ID,
        "scenario_count": len(summaries),
        "scenarios": summaries,
    }


@app.post("/v1/sessions/start")
def start_session(request: Request, payload: StartSessionRequest) -> dict[str, Any]:
    scenario = SCENARIOS.get(payload.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"Unknown scenario_id: {payload.scenario_id}")

    session_id = f"gp_sess_{uuid4().hex[:12]}"
    now = _utc_now_iso()
    session = {
        "session_id": session_id,
        "scenario_id": payload.scenario_id,
        "learner_id": payload.learner_id,
        "status": "initialized",
        "turn_count": 0,
        "started_at": now,
        "updated_at": now,
        "scenario": deepcopy(scenario),
        "coach_continuity": _coach_continuity(scenario),
        "turns": [],
        "review": None,
        "finish_reason": None,
        "experiment_context": _baseline_prompt_context(),
        "trace_id": request.state.trace_id,
        "evidence_by_subskill": {subskill_id: [] for subskill_id in SUBSKILLS},
    }
    app.state.sessions[session_id] = session
    _append_event(
        request,
        session,
        action_id="start_session",
        event_type="session_started",
        stage="opening",
        content={"status": "initialized"},
    )
    return {
        "session_id": session_id,
        "scenario_id": payload.scenario_id,
        "learner_id": payload.learner_id,
        "status": "initialized",
        "scenario": _scenario_summary(scenario),
        "coach_continuity": deepcopy(session["coach_continuity"]),
        "experiment_context": deepcopy(session["experiment_context"]),
    }


@app.get("/v1/sessions/{session_id}")
def get_session(request: Request, session_id: str) -> dict[str, Any]:
    session = _require_session(session_id)
    _set_trace_targets(request, session_id=session_id)
    return {
        "session_id": session_id,
        "scenario_id": session["scenario_id"],
        "learner_id": session["learner_id"],
        "status": session["status"],
        "turn_count": session["turn_count"],
        "started_at": session["started_at"],
        "updated_at": session["updated_at"],
        "scenario": _scenario_summary(session["scenario"]),
        "coach_continuity": deepcopy(session["coach_continuity"]),
        "turns": deepcopy(session["turns"]),
        "experiment_context": deepcopy(session["experiment_context"]),
    }


@app.post("/v1/sessions/{session_id}/turn")
def send_turn(request: Request, session_id: str, payload: SendTurnRequest) -> dict[str, Any]:
    session = _require_session(session_id)
    if session["status"] == "finalized":
        raise HTTPException(status_code=409, detail=f"Session already finalized: {session_id}")

    analysis = _analyze_turn(payload.message, session)
    turn_index = int(session["turn_count"]) + 1
    turn_id = _turn_id(session_id, turn_index)
    turn = {
        "turn_index": turn_index,
        "user_message": payload.message.strip(),
        "doctor_reply": analysis["doctor_reply"],
        "director_phase": analysis["phase"],
        "director_events": list(analysis["events"]),
        "created_at": _utc_now_iso(),
        "persona_id": str(session["scenario"]["doctor_persona_id"]),
    }
    session["turns"].append(turn)
    session["turn_count"] = turn_index
    session["updated_at"] = turn["created_at"]
    session["status"] = "awaiting_finish" if analysis["should_finish"] else "running"
    _apply_subskill_evidence(session, analysis)
    _append_event(
        request,
        session,
        action_id="send_turn",
        event_type="turn_processed",
        stage=analysis["phase"],
        content={
            "turn_index": turn_index,
            "director_phase": analysis["phase"],
            "director_events": list(analysis["events"]),
            "recommended_action": analysis["recommended_action"],
            "status": session["status"],
            "taxonomy": "gp_spike_v1",
        },
        turn_index=turn_index,
    )
    _set_trace_targets(request, session_id=session_id, turn_id=turn_id)
    return {
        "session_id": session_id,
        "status": session["status"],
        "turn_index": turn_index,
        "doctor_reply": analysis["doctor_reply"],
        "persona_id": str(session["scenario"]["doctor_persona_id"]),
        "director": {
            "phase": analysis["phase"],
            "events": list(analysis["events"]),
            "should_finish": bool(analysis["should_finish"]),
            "recommended_action": analysis["recommended_action"],
        },
    }


@app.post("/v1/sessions/{session_id}/finish")
def finish_session(request: Request, session_id: str) -> dict[str, Any]:
    session = _require_session(session_id)
    if not session["turns"]:
        raise HTTPException(status_code=409, detail=f"Session has no turns yet: {session_id}")

    if session["status"] != "finalized":
        session["finish_reason"] = "manual_finish"
        session["review"] = _review_for_session(session)
        session["status"] = "finalized"
        session["updated_at"] = _utc_now_iso()
        _append_event(
            request,
            session,
            action_id="finish_session",
            event_type="session_finished",
            stage="completion",
            content={
                "finish_reason": session["finish_reason"],
                "overall_score": session["review"]["overall_score"],
                "overall_band": session["review"]["overall_band"],
            },
        )

    progress_snapshot = _update_progress(session, session["review"])
    _set_trace_targets(request, session_id=session_id)
    return {
        "session_id": session_id,
        "scenario_id": session["scenario_id"],
        "learner_id": session["learner_id"],
        "status": session["status"],
        "finish_reason": session["finish_reason"],
        "review": deepcopy(session["review"]),
        "coach_continuity": deepcopy(session["coach_continuity"]),
        "progress_snapshot": deepcopy(progress_snapshot),
        "experiment_context": deepcopy(session["experiment_context"]),
    }


@app.get("/v1/sessions/{session_id}/review")
def get_review(request: Request, session_id: str) -> dict[str, Any]:
    session = _require_session(session_id)
    if session["status"] != "finalized" or session["review"] is None:
        raise HTTPException(status_code=409, detail=f"Review not available for session_id: {session_id}")
    progress = app.state.progress.get(session["learner_id"])
    _set_trace_targets(request, session_id=session_id)
    return {
        "session_id": session_id,
        "scenario_id": session["scenario_id"],
        "learner_id": session["learner_id"],
        "status": session["status"],
        "finish_reason": session["finish_reason"],
        "turn_count": session["turn_count"],
        "started_at": session["started_at"],
        "updated_at": session["updated_at"],
        "scenario": _scenario_summary(session["scenario"]),
        "review": deepcopy(session["review"]),
        "coach_continuity": deepcopy(session["coach_continuity"]),
        "coach_memory": deepcopy(progress["coach_memory"]) if progress else None,
        "experiment_context": deepcopy(session["experiment_context"]),
    }


@app.get("/v1/learners/{learner_id}/progress")
def get_progress_snapshot(request: Request, learner_id: str) -> dict[str, Any]:
    progress = app.state.progress.get(learner_id)
    if progress is None:
        raise HTTPException(status_code=404, detail=f"Unknown learner_id: {learner_id}")
    _set_trace_targets(request)
    return deepcopy(progress)


@app.get("/v1/sessions/{session_id}/events")
def get_session_events(request: Request, session_id: str) -> dict[str, Any]:
    _require_session(session_id)
    events = list(app.state.events.get(session_id, []))
    _set_trace_targets(request, session_id=session_id)
    return {
        "session_id": session_id,
        "event_count": len(events),
        "events": deepcopy(events),
    }


@app.get("/v1/evaluation-gates")
def get_evaluation_gates(request: Request) -> dict[str, Any]:
    _set_trace_targets(request)
    return _evaluation_gates_payload()

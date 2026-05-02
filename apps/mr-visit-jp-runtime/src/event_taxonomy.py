from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_PERMISSION_KEYWORDS = (
    "may i",
    "can i",
    "if i may",
    "with your permission",
    "briefly",
    "one minute",
    "30 seconds",
)
_QUESTION_KEYWORDS = (
    "?",
    "what matters",
    "which patients",
    "how are",
    "what are you seeing",
    "do you see",
    "would it be useful",
    "could you share",
)
_PATIENT_SEGMENT_KEYWORDS = (
    "patient segment",
    "patient profile",
    "patient group",
    "for which patients",
    "which patients",
    "patient type",
    "subgroup",
    "population",
    "patients with",
    "patient",
    "patients",
)
_EVIDENCE_KEYWORDS = (
    "evidence",
    "data",
    "study",
    "trial",
    "guideline",
    "publication",
    "analysis",
    "real-world",
    "real world",
)
_ENDPOINT_KEYWORDS = (
    "endpoint",
    "endpoints",
    "overall survival",
    "progression-free survival",
    "pfs",
    "os",
    "hazard ratio",
    "response rate",
    "median",
    "safety profile",
    "adverse event rate",
)
_NEXT_STEP_KEYWORDS = (
    "next step",
    "follow-up",
    "follow up",
    "send",
    "share",
    "review",
    "meet",
    "check in",
    "call",
    "come back",
)
_PRACTICAL_RELEVANCE_KEYWORDS = (
    "daily patients",
    "current patients",
    "in your practice",
    "in your clinic",
    "workflow",
    "practical",
    "relevant",
    "today",
)
_COMPARISON_KEYWORDS = (
    "competitor",
    "current standard",
    "standard of care",
    "versus",
    "vs",
    "why change",
    "compared with",
    "compared to",
)
_ATTACK_COMPARISON_KEYWORDS = (
    "better than",
    "superior",
    "inferior",
    "worse than",
    "beats",
    "outperforms",
    "replace the competitor",
)
_SAFETY_KEYWORDS = (
    "adverse event",
    "safety",
    "report",
    "reporting",
    "pharmacovigilance",
    "follow-up process",
    "follow up process",
)
_PRIOR_CONTEXT_KEYWORDS = (
    "last time",
    "previous",
    "prior",
    "before",
    "earlier",
    "we discussed",
    "we spoke",
    "after our last",
)
_NEW_RELEVANCE_KEYWORDS = (
    "new data",
    "new evidence",
    "updated",
    "different now",
    "since last time",
    "has changed",
)
_FORMULARY_KEYWORDS = (
    "formulary",
    "pathway",
    "restriction",
    "access",
    "committee",
    "institution",
    "hospital",
    "listing",
    "coverage",
)
_LARGE_COMMITMENT_KEYWORDS = (
    "switch all",
    "all your patients",
    "all patients",
    "replace",
    "move everyone",
    "adopt broadly",
    "wide adoption",
    "change practice now",
)
_MICRO_COMMITMENT_KEYWORDS = (
    "one patient",
    "a few patients",
    "review one case",
    "review a case",
    "short follow-up",
    "short follow up",
    "pilot",
    "limited trial",
    "small step",
    "next week",
    "brief follow-up",
    "share one paper",
)
_FOLLOWUP_PROCESS_KEYWORDS = (
    "follow-up process",
    "follow up process",
    "reporting process",
    "capture the event",
    "document",
    "escalate",
    "escalation",
    "safety team",
    "pharmacovigilance",
    "internal follow-up",
)
_CLAIM_KEYWORDS = (
    "works well",
    "works very well",
    "strong",
    "effective",
    "benefit",
    "improves",
    "superior",
    "better",
    "should matter",
    "should use",
    "change practice",
)
_UNCERTAINTY_KEYWORDS = (
    "may",
    "might",
    "could",
    "suggests",
    "signal",
    "limited",
    "not powered",
    "uncertain",
    "modest",
)
_NUMERIC_DETAIL_RE = re.compile(r"\b\d+(?:[./-]\d+)?%?\b")

EVENT_CATEGORY_ORDER = (
    "opening",
    "profiling",
    "evidence",
    "objection",
    "compliance",
    "closing",
    "recovery",
    "completion",
)

PHASE_CATEGORY_MAP = {
    "opening": "opening",
    "discovery": "profiling",
    "evidence": "evidence",
    "safety": "compliance",
    "closing": "closing",
}

DIRECTOR_EVENT_TAXONOMY: dict[str, dict[str, str]] = {
    "opening_overlong": {
        "category": "opening",
        "severity": "warning",
        "description": "Opening consumed too much space before value or permission was clear.",
    },
    "low_information_turn": {
        "category": "recovery",
        "severity": "warning",
        "description": "Turn did not provide enough actionable information to continue cleanly.",
    },
    "patient_segment_not_specified": {
        "category": "opening",
        "severity": "warning",
        "description": "Opening did not define the patient segment or target profile.",
    },
    "opening_missing_permission": {
        "category": "opening",
        "severity": "warning",
        "description": "Opening did not ask permission or frame the visit tightly.",
    },
    "evidence_not_addressed": {
        "category": "evidence",
        "severity": "warning",
        "description": "Evidence-demanding persona did not receive a concrete data anchor.",
    },
    "safety_first_context": {
        "category": "compliance",
        "severity": "info",
        "description": "Scenario context shifted into safety and reporting first.",
    },
    "safety_reporting_not_started": {
        "category": "compliance",
        "severity": "critical",
        "description": "Safety scenario still lacks the reporting or follow-up process.",
    },
    "practical_relevance_not_established": {
        "category": "recovery",
        "severity": "warning",
        "description": "Message has not yet connected to day-to-day clinical relevance.",
    },
    "prior_rejection_not_acknowledged": {
        "category": "objection",
        "severity": "warning",
        "description": "Learner did not acknowledge prior pushback before retrying the message.",
    },
    "no_new_relevance_after_rejection": {
        "category": "objection",
        "severity": "warning",
        "description": "Retry message did not explain what changed since the earlier rejection.",
    },
    "formulary_barrier_not_explored": {
        "category": "profiling",
        "severity": "warning",
        "description": "System or formulary constraints were not explored before pitching harder.",
    },
    "commitment_too_large_for_cautious_persona": {
        "category": "objection",
        "severity": "warning",
        "description": "Suggested next move asked for too much commitment too early.",
    },
    "closing_next_step_missing": {
        "category": "closing",
        "severity": "warning",
        "description": "Closing phase lacks a concrete next step and follow-up path.",
    },
    "carryover_opening_gap": {
        "category": "opening",
        "severity": "warning",
        "description": "Prior opening weakness is still visible in this turn.",
    },
    "time_pressure_not_respected": {
        "category": "opening",
        "severity": "warning",
        "description": "Message did not adapt to the persona's time constraint.",
    },
    "carryover_need_discovery_gap": {
        "category": "profiling",
        "severity": "warning",
        "description": "Carryover discovery weakness is still unresolved.",
    },
    "weak_profiling_signal": {
        "category": "profiling",
        "severity": "warning",
        "description": "Turn did not surface a concrete decision criterion or need signal.",
    },
    "discovery_question_missing": {
        "category": "profiling",
        "severity": "warning",
        "description": "Learner continued talking without asking a concrete discovery question.",
    },
    "carryover_evidence_gap": {
        "category": "evidence",
        "severity": "warning",
        "description": "Carryover evidence weakness is still unresolved.",
    },
    "evidence_detail_missing": {
        "category": "evidence",
        "severity": "warning",
        "description": "Evidence was mentioned without the endpoint, safety, or use-case detail needed here.",
    },
    "evidence_dump_without_use_case": {
        "category": "evidence",
        "severity": "warning",
        "description": "Turn listed evidence without connecting it to the patient use case or next move.",
    },
    "unsupported_claim_without_evidence": {
        "category": "evidence",
        "severity": "warning",
        "description": "Clinical claim was made without a supporting study, endpoint, or limitation.",
    },
    "patient_use_case_not_defined": {
        "category": "evidence",
        "severity": "warning",
        "description": "Evidence was not tied to a clearly defined patient use case.",
    },
    "decision_criteria_not_explored": {
        "category": "profiling",
        "severity": "warning",
        "description": "Turn skipped the doctor's decision criteria before comparing options.",
    },
    "unsupported_competitor_comparison": {
        "category": "objection",
        "severity": "warning",
        "description": "Competitor comparison was asserted without support or without reframing constructively.",
    },
    "need_signal_not_established": {
        "category": "recovery",
        "severity": "warning",
        "description": "Turn did not earn interest by linking to an immediate clinical need.",
    },
    "followup_process_not_stated": {
        "category": "compliance",
        "severity": "critical",
        "description": "Safety follow-up process or escalation path was not stated clearly.",
    },
    "micro_commitment_missing": {
        "category": "closing",
        "severity": "warning",
        "description": "Closing move lacked a limited, realistic micro-commitment.",
    },
    "unrealistic_adoption_request": {
        "category": "objection",
        "severity": "warning",
        "description": "Requested adoption step was unrealistic for the current system constraints.",
    },
    "carryover_followup_gap": {
        "category": "closing",
        "severity": "warning",
        "description": "Carryover follow-up weakness is still unresolved.",
    },
    "max_turns_reached": {
        "category": "completion",
        "severity": "info",
        "description": "Session reached the configured turn budget and should wrap up.",
    },
}

LIFECYCLE_EVENT_TAXONOMY: dict[str, dict[str, str]] = {
    "session_started": {
        "category": "opening",
        "severity": "info",
        "description": "Practice session started and is ready for the opening turn.",
    },
    "session_finalized": {
        "category": "completion",
        "severity": "info",
        "description": "Practice session finished and review/progress artifacts are available.",
    },
}


def _message_contains_any(message: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in message for keyword in keywords)


@dataclass(frozen=True)
class TurnSignals:
    token_count: int
    has_question: bool
    has_permission: bool
    has_patient_segment: bool
    has_evidence: bool
    has_endpoint_detail: bool
    has_next_step: bool
    has_micro_commitment: bool
    has_practical_relevance: bool
    has_safety_signal: bool
    has_followup_process: bool
    acknowledges_prior_context: bool
    shows_new_relevance: bool
    has_formulary_context: bool
    has_comparison_context: bool
    has_attack_comparison: bool
    has_claim_language: bool
    has_uncertainty_language: bool
    requests_large_commitment: bool

    def to_dict(self) -> dict[str, Any]:
        present_signals = [
            signal_name
            for signal_name, active in (
                ("question", self.has_question),
                ("permission", self.has_permission),
                ("patient_segment", self.has_patient_segment),
                ("evidence", self.has_evidence),
                ("endpoint_detail", self.has_endpoint_detail),
                ("next_step", self.has_next_step),
                ("micro_commitment", self.has_micro_commitment),
                ("practical_relevance", self.has_practical_relevance),
                ("safety", self.has_safety_signal),
                ("followup_process", self.has_followup_process),
                ("prior_context", self.acknowledges_prior_context),
                ("new_relevance", self.shows_new_relevance),
                ("formulary_context", self.has_formulary_context),
                ("comparison_context", self.has_comparison_context),
                ("claim_language", self.has_claim_language),
                ("uncertainty_language", self.has_uncertainty_language),
            )
            if active
        ]
        missing_core_signals = [
            signal_name
            for signal_name, active in (
                ("permission", self.has_permission),
                ("patient_segment", self.has_patient_segment),
                ("question", self.has_question),
                ("evidence", self.has_evidence),
                ("next_step", self.has_next_step),
            )
            if not active
        ]
        if self.has_evidence and not self.has_endpoint_detail:
            missing_core_signals.append("endpoint_detail")
        if self.has_next_step and not self.has_micro_commitment:
            missing_core_signals.append("micro_commitment")
        if self.has_safety_signal and not self.has_followup_process:
            missing_core_signals.append("followup_process")
        return {
            "token_count": self.token_count,
            "has_question": self.has_question,
            "has_permission": self.has_permission,
            "has_patient_segment": self.has_patient_segment,
            "has_evidence": self.has_evidence,
            "has_endpoint_detail": self.has_endpoint_detail,
            "has_next_step": self.has_next_step,
            "has_micro_commitment": self.has_micro_commitment,
            "has_practical_relevance": self.has_practical_relevance,
            "has_safety_signal": self.has_safety_signal,
            "has_followup_process": self.has_followup_process,
            "acknowledges_prior_context": self.acknowledges_prior_context,
            "shows_new_relevance": self.shows_new_relevance,
            "has_formulary_context": self.has_formulary_context,
            "has_comparison_context": self.has_comparison_context,
            "has_attack_comparison": self.has_attack_comparison,
            "has_claim_language": self.has_claim_language,
            "has_uncertainty_language": self.has_uncertainty_language,
            "requests_large_commitment": self.requests_large_commitment,
            "present_signals": present_signals,
            "missing_core_signals": missing_core_signals,
        }


def analyze_turn_message(message: str) -> TurnSignals:
    lowered = message.lower()
    token_count = len(message.split())
    has_question = _message_contains_any(lowered, _QUESTION_KEYWORDS)
    has_permission = _message_contains_any(lowered, _PERMISSION_KEYWORDS)
    has_patient_segment = _message_contains_any(lowered, _PATIENT_SEGMENT_KEYWORDS)
    has_evidence = _message_contains_any(lowered, _EVIDENCE_KEYWORDS)
    has_endpoint_detail = _message_contains_any(lowered, _ENDPOINT_KEYWORDS) or (
        has_evidence and _NUMERIC_DETAIL_RE.search(lowered) is not None
    )
    has_next_step = _message_contains_any(lowered, _NEXT_STEP_KEYWORDS)
    has_micro_commitment = has_next_step and _message_contains_any(
        lowered,
        _MICRO_COMMITMENT_KEYWORDS,
    )
    has_practical_relevance = has_patient_segment or _message_contains_any(
        lowered,
        _PRACTICAL_RELEVANCE_KEYWORDS,
    )
    has_safety_signal = _message_contains_any(lowered, _SAFETY_KEYWORDS)
    has_followup_process = _message_contains_any(lowered, _FOLLOWUP_PROCESS_KEYWORDS)
    acknowledges_prior_context = _message_contains_any(lowered, _PRIOR_CONTEXT_KEYWORDS)
    shows_new_relevance = _message_contains_any(lowered, _NEW_RELEVANCE_KEYWORDS)
    has_formulary_context = _message_contains_any(lowered, _FORMULARY_KEYWORDS)
    has_comparison_context = _message_contains_any(lowered, _COMPARISON_KEYWORDS)
    has_attack_comparison = _message_contains_any(lowered, _ATTACK_COMPARISON_KEYWORDS)
    has_claim_language = _message_contains_any(lowered, _CLAIM_KEYWORDS)
    has_uncertainty_language = _message_contains_any(lowered, _UNCERTAINTY_KEYWORDS)
    requests_large_commitment = _message_contains_any(lowered, _LARGE_COMMITMENT_KEYWORDS)
    return TurnSignals(
        token_count=token_count,
        has_question=has_question,
        has_permission=has_permission,
        has_patient_segment=has_patient_segment,
        has_evidence=has_evidence,
        has_endpoint_detail=has_endpoint_detail,
        has_next_step=has_next_step,
        has_micro_commitment=has_micro_commitment,
        has_practical_relevance=has_practical_relevance,
        has_safety_signal=has_safety_signal,
        has_followup_process=has_followup_process,
        acknowledges_prior_context=acknowledges_prior_context,
        shows_new_relevance=shows_new_relevance,
        has_formulary_context=has_formulary_context,
        has_comparison_context=has_comparison_context,
        has_attack_comparison=has_attack_comparison,
        has_claim_language=has_claim_language,
        has_uncertainty_language=has_uncertainty_language,
        requests_large_commitment=requests_large_commitment,
    )


def director_taxonomy_entries(event_codes: list[str]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for code in event_codes:
        if code in seen:
            continue
        seen.add(code)
        payload = DIRECTOR_EVENT_TAXONOMY.get(
            code,
            {
                "category": "recovery",
                "severity": "info",
                "description": "Unmapped runtime event.",
            },
        )
        entries.append(
            {
                "code": code,
                "category": payload["category"],
                "severity": payload["severity"],
                "description": payload["description"],
            }
        )
    return entries


def lifecycle_taxonomy_entries(event_type: str) -> list[dict[str, str]]:
    payload = LIFECYCLE_EVENT_TAXONOMY.get(event_type)
    if payload is None:
        return []
    return [
        {
            "code": event_type,
            "category": payload["category"],
            "severity": payload["severity"],
            "description": payload["description"],
        }
    ]


def director_taxonomy_categories(
    *,
    phase: str,
    event_codes: list[str],
    recommended_action: str,
    should_finish: bool,
) -> list[str]:
    categories: list[str] = []

    def add_category(category: str) -> None:
        if category and category not in categories:
            categories.append(category)

    add_category(PHASE_CATEGORY_MAP.get(phase, ""))
    for entry in director_taxonomy_entries(event_codes):
        add_category(entry["category"])
    if event_codes and recommended_action not in {"continue", "finish_session"}:
        add_category("recovery")
    if should_finish or "max_turns_reached" in event_codes:
        add_category("completion")

    ordered = [category for category in EVENT_CATEGORY_ORDER if category in categories]
    extras = [category for category in categories if category not in EVENT_CATEGORY_ORDER]
    return [*ordered, *extras]


def build_turn_event_content(
    *,
    turn_index: int,
    phase: str,
    event_codes: list[str],
    recommended_action: str,
    should_finish: bool,
    turn_signals: TurnSignals,
) -> dict[str, Any]:
    taxonomy_entries = director_taxonomy_entries(event_codes)
    taxonomy_categories = director_taxonomy_categories(
        phase=phase,
        event_codes=event_codes,
        recommended_action=recommended_action,
        should_finish=should_finish,
    )
    return {
        "turn_index": turn_index,
        "director_phase": phase,
        "director_events": list(event_codes),
        "recommended_action": recommended_action,
        "director": {
            "phase": phase,
            "events": list(event_codes),
            "recommended_action": recommended_action,
            "should_finish": should_finish,
        },
        "signal_summary": turn_signals.to_dict(),
        "taxonomy": {
            "categories": taxonomy_categories,
            "entries": taxonomy_entries,
        },
    }


def build_session_started_content(
    *,
    experiment_context: dict[str, Any],
    coach_continuity: dict[str, Any],
) -> dict[str, Any]:
    return {
        "experiment_context": experiment_context,
        "coach_continuity": coach_continuity,
        "taxonomy": {
            "categories": ["opening"],
            "entries": lifecycle_taxonomy_entries("session_started"),
        },
    }


def build_session_finalized_content(
    *,
    finish_reason: str,
    overall_score: int,
    experiment_context: dict[str, Any],
) -> dict[str, Any]:
    entries = lifecycle_taxonomy_entries("session_finalized")
    if finish_reason == "max_turns_reached":
        entries.extend(director_taxonomy_entries(["max_turns_reached"]))
    return {
        "finish_reason": finish_reason,
        "overall_score": overall_score,
        "experiment_context": experiment_context,
        "taxonomy": {
            "categories": ["completion"],
            "entries": entries,
        },
    }

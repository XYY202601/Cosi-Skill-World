from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any

from event_taxonomy import (
    TurnSignals,
    analyze_turn_message,
    build_session_finalized_content,
    build_session_started_content,
    build_turn_event_content,
    director_taxonomy_categories,
    director_taxonomy_entries,
)
from evaluation.review_builder import build_runtime_review
from persistence.interfaces import EventStore, SessionStore, SessionStoreConflictError
from providers import summarize_prompt_context
from providers.model_artifact_generator import ModelArtifactGenerationError
from runtime_context import DomainSessionContext, build_turn_id
from scenarios.asset_loader import PlaybookRecord, ScenarioRecord
from session_events import build_session_event_payload


class SessionStatus(str, Enum):
    INITIALIZED = "initialized"
    RUNNING = "running"
    AWAITING_FINISH = "awaiting_finish"
    FINALIZED = "finalized"


class SessionNotFoundError(KeyError):
    pass


class SessionTransitionError(RuntimeError):
    pass


class SessionEvaluationError(RuntimeError):
    pass


class SessionReviewUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class TurnRecord:
    turn_index: int
    user_message: str
    doctor_reply: str
    director_phase: str
    director_events: list[str]
    created_at: str
    persona_id: str | None = None


@dataclass
class SessionRecord:
    session_id: str
    scenario_id: str
    learner_id: str
    prompt_context: dict[str, Any]
    continuity_context: dict[str, Any]
    context: DomainSessionContext
    status: SessionStatus
    started_at: str
    updated_at: str
    turn_count: int = 0
    finish_reason: str | None = None
    turns: list[TurnRecord] = field(default_factory=list)
    review: dict[str, Any] | None = None


@dataclass(frozen=True)
class DirectorDecision:
    phase: str
    events: list[str]
    should_finish: bool
    recommended_action: str
    taxonomy_categories: list[str]
    taxonomy_entries: list[dict[str, str]]
    turn_signals: TurnSignals


@dataclass(frozen=True)
class SendTurnResult:
    session_id: str
    status: SessionStatus
    turn_index: int
    doctor_reply: str
    director: DirectorDecision


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalize_prompt_context(prompt_context: Any) -> dict[str, Any]:
    if not isinstance(prompt_context, dict):
        return {}
    return deepcopy(prompt_context)


def _normalize_continuity_context(continuity_context: Any) -> dict[str, Any]:
    if not isinstance(continuity_context, dict):
        return {}
    return deepcopy(continuity_context)


_SUBSKILL_HINTS_BY_LOCALE = {
    "en": {
        "opening": "Ask permission, name the patient segment, and make one relevant point.",
        "profiling": "Ask what constraint is actually shaping the decision here.",
        "scientific_delivery": "Use one evidence-backed point and make the patient segment explicit.",
        "need_discovery": "Ask one targeted context question before you pitch.",
        "objection_handling": "Acknowledge the pushback first, then answer with specific support.",
        "closing_followup": "State one concrete next step and the follow-up path.",
        "__default__": "Keep the next move specific, relevant, and easy to act on.",
    },
    "ja": {
        "opening": "許可を取り、対象患者像を示し、関連性の高い要点を1つ伝えてください。",
        "profiling": "意思決定を左右している制約条件を先に確認してください。",
        "scientific_delivery": "根拠となるデータを1点示し、対象患者像を明確にしてください。",
        "need_discovery": "提案前に、文脈に沿った具体的な質問を1つしてください。",
        "objection_handling": "まず懸念を受け止め、その上で具体的根拠で回答してください。",
        "closing_followup": "次の具体的アクションを1つ示し、フォロー方法を明確にしてください。",
        "__default__": "次の一手は、具体的で関連性があり実行しやすい形にしてください。",
    },
    "zh": {
        "opening": "先征得许可，说明目标患者人群，再给出一个高相关要点。",
        "profiling": "先问清真正影响决策的限制条件是什么。",
        "scientific_delivery": "给出一个有证据支撑的要点，并明确适用患者人群。",
        "need_discovery": "先问一个有针对性的需求问题，再继续讲解。",
        "objection_handling": "先承接医生异议，再用具体证据回应。",
        "closing_followup": "明确一个具体下一步，并说明后续跟进路径。",
        "__default__": "下一步请保持具体、相关、可执行。",
    },
}


def _reply_locale_key(locale: str | None) -> str:
    normalized = str(locale or "").strip().lower()
    if normalized.startswith("ja"):
        return "ja"
    if normalized.startswith("zh"):
        return "zh"
    return "en"


def _localized_text(
    *,
    locale_key: str,
    en: str,
    ja: str,
    zh: str,
) -> str:
    if locale_key == "ja":
        return ja
    if locale_key == "zh":
        return zh
    return en


def _contains_cjk_characters(value: str) -> bool:
    return any(
        "\u3040" <= char <= "\u30ff"
        or "\u3400" <= char <= "\u9fff"
        for char in value
    )


@dataclass(frozen=True)
class _HeuristicContext:
    focus_subskills: set[str]
    failure_patterns: set[str]
    success_criteria: set[str]
    playbook: PlaybookRecord | None = None


def _string_set(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {
        item.strip()
        for item in values
        if isinstance(item, str) and item.strip()
    }


def _build_heuristic_context(
    continuity_context: dict[str, Any],
    scenario: ScenarioRecord | None = None,
) -> _HeuristicContext:
    focus_subskills = _string_set(continuity_context.get("scenario_focus_subskills"))
    if not focus_subskills:
        focus_subskills = _string_set(continuity_context.get("suggested_focus_subskills"))
    if not focus_subskills and scenario and scenario.playbook is not None:
        focus_subskills = set(scenario.playbook.target_subskills)
    if not focus_subskills and scenario:
        focus_subskills = set(scenario.focus_subskills)

    failure_patterns = _string_set(continuity_context.get("failure_patterns"))
    if not failure_patterns and scenario:
        failure_patterns = set(scenario.failure_patterns)

    success_criteria = _string_set(continuity_context.get("success_criteria"))
    if not success_criteria and scenario:
        success_criteria = set(scenario.success_criteria)

    return _HeuristicContext(
        focus_subskills=focus_subskills,
        failure_patterns=failure_patterns,
        success_criteria=success_criteria,
        playbook=scenario.playbook if scenario else None,
    )


def _playbook_strings(
    playbook: PlaybookRecord | None,
    *,
    fields: tuple[str, ...],
) -> list[str]:
    if playbook is None:
        return []

    values: list[str] = []
    for field_name in fields:
        value = getattr(playbook, field_name, None)
        if isinstance(value, str):
            if value.strip():
                values.append(value.strip().lower())
            continue
        if isinstance(value, list):
            values.extend(
                item.strip().lower()
                for item in value
                if isinstance(item, str) and item.strip()
            )
    return values


def _playbook_contains(
    playbook: PlaybookRecord | None,
    *,
    fields: tuple[str, ...],
    keywords: tuple[str, ...],
) -> bool:
    values = _playbook_strings(playbook, fields=fields)
    return any(keyword in value for value in values for keyword in keywords)


def _playbook_first_list_item(
    playbook: PlaybookRecord | None,
    field_name: str,
) -> str | None:
    if playbook is None:
        return None
    value = getattr(playbook, field_name, None)
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


def _playbook_requires_safety_reporting(playbook: PlaybookRecord | None) -> bool:
    return _playbook_contains(
        playbook,
        fields=(
            "learning_objective",
            "expected_flow",
            "common_failure_patterns",
            "recovery_moves",
        ),
        keywords=("adverse event", "report", "reporting", "escalation"),
    )


def _playbook_requires_prior_context(playbook: PlaybookRecord | None) -> bool:
    return _playbook_contains(
        playbook,
        fields=("learning_objective", "expected_flow", "common_failure_patterns"),
        keywords=("previous", "prior rejection", "last time", "re-engage"),
    )


def _playbook_requires_formulary_discovery(playbook: PlaybookRecord | None) -> bool:
    return _playbook_contains(
        playbook,
        fields=("learning_objective", "expected_flow", "key_discovery_questions"),
        keywords=("formulary", "committee", "pathway", "hospital"),
    )


def _prefers_early_close(
    *,
    time_pressure: str,
    heuristic_context: _HeuristicContext,
) -> bool:
    return (
        time_pressure == "high" and "closing_followup" in heuristic_context.focus_subskills
    ) or _playbook_contains(
        heuristic_context.playbook,
        fields=("learning_objective", "expected_flow", "completion_signals"),
        keywords=("follow-up appointment", "follow-up time", "doctor leaves", "be brief"),
    )


def _needs_discovery_signal(heuristic_context: _HeuristicContext) -> bool:
    if (
        heuristic_context.playbook is not None
        and heuristic_context.playbook.key_discovery_questions
        and {"profiling", "need_discovery"} & set(heuristic_context.playbook.target_subskills)
    ):
        return True
    return bool({"profiling", "need_discovery"} & heuristic_context.focus_subskills)


def _needs_evidence_detail(
    *,
    attitude: str,
    decision_style: str,
    heuristic_context: _HeuristicContext,
) -> bool:
    return (
        "scientific_delivery" in heuristic_context.focus_subskills
        or "objection_handling" in heuristic_context.focus_subskills
        or (
            heuristic_context.playbook is not None
            and heuristic_context.playbook.acceptable_evidence_moves
            and {
                "scientific_delivery",
                "objection_handling",
            }
            & set(heuristic_context.playbook.target_subskills)
        )
        or attitude in {"skeptical", "cautious"}
        or decision_style in {"evidence_first", "comparison_driven", "risk_averse"}
    )


def _needs_micro_commitment(
    *,
    heuristic_context: _HeuristicContext,
    persona: dict[str, Any],
) -> bool:
    return (
        "closing_followup" in heuristic_context.focus_subskills
        or str(persona.get("decision_style", "")) in {"pragmatic", "risk_averse", "system_constraint_driven"}
        or "concrete_followup_commitment" in heuristic_context.success_criteria
        or "gains_micro_commitment_for_trial" in heuristic_context.success_criteria
        or _playbook_contains(
            heuristic_context.playbook,
            fields=("learning_objective", "expected_flow", "completion_signals"),
            keywords=("micro-commitment", "specific follow-up time", "specific realistic action", "try the product"),
        )
    )


def _supports_competitor_reframe(
    *,
    decision_style: str,
    heuristic_context: _HeuristicContext,
) -> bool:
    return (
        decision_style == "comparison_driven"
        or "surfaces_decision_criteria" in heuristic_context.success_criteria
        or "reframes_without_negative_competitor_claim" in heuristic_context.success_criteria
        or _playbook_contains(
            heuristic_context.playbook,
            fields=("learning_objective", "expected_flow", "key_discovery_questions"),
            keywords=("competitor", "decision criteria"),
        )
    )




def _continuity_action_hint(
    continuity_context: dict[str, Any],
    preferred_subskill: str,
    heuristic_context: _HeuristicContext | None = None,
    locale: str | None = None,
) -> str:
    locale_key = _reply_locale_key(locale)

    def _hint_matches_locale(candidate: str) -> bool:
        if locale_key == "en":
            return True
        return _contains_cjk_characters(candidate)

    # 1. Try playbook-specific recovery moves if we are in a failure pattern
    if heuristic_context and heuristic_context.playbook and heuristic_context.playbook.recovery_moves:
        # For now, just pick the first one if we have any active failure patterns
        # In a real implementation, we'd map patterns to specific moves.
        if heuristic_context.failure_patterns:
            candidate = str(heuristic_context.playbook.recovery_moves[0]).strip()
            if candidate and _hint_matches_locale(candidate):
                return candidate

    # 2. Try continuity-specific next actions from learner history
    suggested_focus = [
        item
        for item in continuity_context.get("suggested_focus_subskills", [])
        if isinstance(item, str)
    ]
    next_actions = [
        item.strip()
        for item in continuity_context.get("next_actions", [])
        if isinstance(item, str) and item.strip()
    ]
    if preferred_subskill in suggested_focus:
        focus_index = suggested_focus.index(preferred_subskill)
        if focus_index < len(next_actions):
            candidate = next_actions[focus_index]
            if candidate and _hint_matches_locale(candidate):
                return candidate
    if next_actions:
        candidate = next_actions[0]
        if candidate and _hint_matches_locale(candidate):
            return candidate

    # 3. Fallback to generic subskill hints
    locale_hints = _SUBSKILL_HINTS_BY_LOCALE.get(
        locale_key,
        _SUBSKILL_HINTS_BY_LOCALE["en"],
    )
    default_hint = str(locale_hints.get("__default__", _SUBSKILL_HINTS_BY_LOCALE["en"]["__default__"]))
    return str(locale_hints.get(preferred_subskill, default_hint))


class SessionEngine:
    """
    In-memory-first session engine for Alpha runtime skeleton.
    Session and event stores are optional adapters for persistence.
    """

    def __init__(
        self,
        session_store: SessionStore | None = None,
        event_store: EventStore | None = None,
    ) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = Lock()
        self._session_store = session_store
        self._event_store = event_store

    def create_session(
        self,
        session_id: str,
        scenario_id: str,
        learner_id: str,
        prompt_context: dict[str, Any] | None = None,
        continuity_context: dict[str, Any] | None = None,
        context: DomainSessionContext | None = None,
        started_at: str | None = None,
    ) -> SessionRecord:
        now = started_at or _utc_now_iso()
        with self._lock:
            normalized_prompt_context = _normalize_prompt_context(prompt_context)
            normalized_continuity_context = _normalize_continuity_context(continuity_context)
            record_context = context or DomainSessionContext.from_session_seed(
                session_id=session_id,
                learner_id=learner_id,
                scenario_id=scenario_id,
                persona_id="",
                prompt_context=normalized_prompt_context,
                continuity_context=normalized_continuity_context,
            )
            record = SessionRecord(
                session_id=session_id,
                scenario_id=scenario_id,
                learner_id=learner_id,
                prompt_context=normalized_prompt_context,
                continuity_context=normalized_continuity_context,
                context=record_context,
                status=SessionStatus.INITIALIZED,
                started_at=now,
                updated_at=now,
            )
            self._sessions[session_id] = record
            if self._session_store is not None:
                try:
                    self._session_store.create(session_id, self._serialize_session(record), org_id=record.context.org_id)
                except SessionStoreConflictError:
                    # Defensive fallback when storage already has this session id.
                    self._session_store.upsert(session_id, self._serialize_session(record), org_id=record.context.org_id)
            started_context = record.context.for_action("start_session")
            self._append_event(
                session_id,
                build_session_event_payload(
                    event_type="session_started",
                    timestamp=now,
                    session_context=started_context,
                    stage="opening",
                    content=build_session_started_content(
                        experiment_context=summarize_prompt_context(record.prompt_context),
                        coach_continuity={
                            "summary": str(record.continuity_context.get("summary", "")),
                            "suggested_focus_subskills": list(
                                record.continuity_context.get("suggested_focus_subskills", [])
                            ),
                            "teaching_plan": record.continuity_context.get("teaching_plan"),
                            "teaching_plan_snapshot": record.continuity_context.get("teaching_plan_snapshot"),
                        },
                    ),
                ),
                org_id=record.context.org_id,
            )
            return record

    def get_session(self, session_id: str, *, org_id: str | None = None) -> SessionRecord:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                if session.context.org_id != org_id:
                    # In-memory session belongs to a different organization.
                    # We treat it as not found to maintain isolation.
                    session = None

            if session is None:
                loaded = self._load_session_from_store(session_id, org_id=org_id)
                if loaded is None:
                    raise SessionNotFoundError(f"Unknown session_id: {session_id}")
                self._sessions[session_id] = loaded
                session = loaded
            return session

    def get_review(self, session_id: str, *, org_id: str | None = None) -> SessionRecord:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and session.context.org_id != org_id:
                session = None

            if session is None:
                loaded = self._load_session_from_store(session_id, org_id=org_id)
                if loaded is None:
                    raise SessionNotFoundError(f"Unknown session_id: {session_id}")
                self._sessions[session_id] = loaded
                session = loaded
            if session.status != SessionStatus.FINALIZED or session.review is None:
                raise SessionReviewUnavailableError(
                    f"Review is unavailable for session_id: {session_id}. "
                    "Finish the session first."
                )
            return session

    def send_turn(
        self,
        session_id: str,
        user_message: str,
        scenario: ScenarioRecord,
        persona: dict[str, Any],
    ) -> SendTurnResult:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                loaded = self._load_session_from_store(session_id)
                if loaded is None:
                    raise SessionNotFoundError(f"Unknown session_id: {session_id}")
                self._sessions[session_id] = loaded
                session = loaded
            if session.status == SessionStatus.FINALIZED:
                raise SessionTransitionError("Session is already finalized.")
            if session.status == SessionStatus.AWAITING_FINISH:
                raise SessionTransitionError("Session reached max turns. Call finish_session.")
            if not user_message.strip():
                raise SessionTransitionError("Turn message cannot be empty.")

            session.status = SessionStatus.RUNNING
            session.turn_count += 1
            decision = self._director_decide(
                turn_count=session.turn_count,
                scenario=scenario,
                user_message=user_message,
                persona=persona,
                continuity_context=session.continuity_context,
            )
            doctor_reply = self._doctor_reply(
                turn_count=session.turn_count,
                user_message=user_message,
                decision=decision,
                persona=persona,
                continuity_context=session.continuity_context,
                scenario=scenario,
                locale=session.context.locale,
            )

            persona_id = persona.get("id") if isinstance(persona, dict) else None
            turn = TurnRecord(
                turn_index=session.turn_count,
                user_message=user_message,
                doctor_reply=doctor_reply,
                director_phase=decision.phase,
                director_events=list(decision.events),
                created_at=_utc_now_iso(),
                persona_id=persona_id,
            )
            session.turns.append(turn)
            session.context = session.context.for_action(
                "send_turn",
                turn_id=build_turn_id(session.session_id, turn.turn_index),
            )
            if decision.should_finish:
                session.status = SessionStatus.AWAITING_FINISH
            session.updated_at = _utc_now_iso()
            self._persist_session(session)
            turn_content = build_turn_event_content(
                turn_index=turn.turn_index,
                phase=decision.phase,
                event_codes=list(decision.events),
                recommended_action=decision.recommended_action,
                should_finish=decision.should_finish,
                turn_signals=decision.turn_signals,
            )
            turn_content["status"] = session.status.value
            self._append_event(
                session_id,
                build_session_event_payload(
                    event_type="turn_processed",
                    timestamp=session.updated_at,
                    session_context=session.context,
                    stage=decision.phase,
                    content=turn_content,
                ),
            )

            return SendTurnResult(
                session_id=session.session_id,
                status=session.status,
                turn_index=turn.turn_index,
                doctor_reply=turn.doctor_reply,
                director=decision,
            )

    def finish_session(
        self,
        session_id: str,
        scenario_focus_subskills: list[str],
        subskill_weights: dict[str, float],
        skill_model: dict[str, Any],
        diagnosis_types: dict[str, Any],
        compliance_rules: dict[str, Any],
        score_schema: dict[str, Any],
        judge_review_schema: dict[str, Any],
        coach_feedback_schema: dict[str, Any],
        compliance_flags_schema: dict[str, Any],
        model_artifact_generator: Any | None = None,
    ) -> SessionRecord:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                loaded = self._load_session_from_store(session_id)
                if loaded is None:
                    raise SessionNotFoundError(f"Unknown session_id: {session_id}")
                self._sessions[session_id] = loaded
                session = loaded
            if session.status == SessionStatus.FINALIZED:
                return session
            if session.status == SessionStatus.INITIALIZED:
                raise SessionTransitionError("Cannot finish session before first turn.")

            finish_reason = (
                "max_turns_reached"
                if session.status == SessionStatus.AWAITING_FINISH
                else "manual_finish"
            )
            session.finish_reason = finish_reason
            session.context = session.context.for_action("finish_session", turn_id=session.context.turn_id)
            try:
                review = self._build_review(
                    session=session,
                    scenario_focus_subskills=scenario_focus_subskills,
                    subskill_weights=subskill_weights,
                    skill_model=skill_model,
                    diagnosis_types=diagnosis_types,
                    compliance_rules=compliance_rules,
                    score_schema=score_schema,
                    judge_review_schema=judge_review_schema,
                    coach_feedback_schema=coach_feedback_schema,
                    compliance_flags_schema=compliance_flags_schema,
                    model_artifact_generator=model_artifact_generator,
                    session_context=session.context,
                )
            except ValueError as exc:
                raise SessionEvaluationError(f"Review artifact validation failed: {exc}") from exc

            session.review = review
            session.status = SessionStatus.FINALIZED
            session.updated_at = _utc_now_iso()
            self._persist_session(session)
            final_content = build_session_finalized_content(
                finish_reason=finish_reason,
                overall_score=int(review.get("overall_score", 0)),
                experiment_context=summarize_prompt_context(session.prompt_context),
            )
            final_content["turn_count"] = session.turn_count
            self._append_event(
                session_id,
                build_session_event_payload(
                    event_type="session_finalized",
                    timestamp=session.updated_at,
                    session_context=session.context,
                    stage="completion",
                    content=final_content,
                ),
            )
            return session

    def _director_decide(
        self,
        turn_count: int,
        scenario: ScenarioRecord,
        user_message: str,
        persona: dict[str, Any],
        continuity_context: dict[str, Any],
    ) -> DirectorDecision:
        max_turns = scenario.max_turns
        signals = analyze_turn_message(user_message)
        attitude = str(persona.get("attitude", "neutral"))
        time_pressure = str(persona.get("time_pressure", ""))
        decision_style = str(persona.get("decision_style", ""))
        heuristic_context = _build_heuristic_context(continuity_context, scenario=scenario)
        playbook_requires_safety = _playbook_requires_safety_reporting(
            heuristic_context.playbook
        )
        playbook_requires_prior_context = _playbook_requires_prior_context(
            heuristic_context.playbook
        )
        playbook_requires_formulary = _playbook_requires_formulary_discovery(
            heuristic_context.playbook
        )
        prefers_early_close = _prefers_early_close(
            time_pressure=time_pressure,
            heuristic_context=heuristic_context,
        )
        needs_discovery = _needs_discovery_signal(heuristic_context)
        needs_evidence = _needs_evidence_detail(
            attitude=attitude,
            decision_style=decision_style,
            heuristic_context=heuristic_context,
        )
        supports_competitor_reframe = _supports_competitor_reframe(
            decision_style=decision_style,
            heuristic_context=heuristic_context,
        )
        closing_threshold = max(2, max_turns - (2 if prefers_early_close else 1))
        if attitude == "concerned" or playbook_requires_safety:
            phase = "safety"
        elif turn_count == 1:
            phase = "opening"
        elif turn_count >= closing_threshold:
            phase = "closing"
        elif supports_competitor_reframe and turn_count <= 2 and not signals.has_question:
            phase = "discovery"
        elif needs_evidence and turn_count >= 2:
            phase = "evidence"
        elif needs_discovery and turn_count <= 2:
            phase = "discovery"
        elif attitude in {"skeptical", "cautious"}:
            phase = "evidence"
        else:
            phase = "discovery"

        events: list[str] = []
        if turn_count == 1 and signals.token_count > 40:
            events.append("opening_overlong")
        if signals.token_count <= 3:
            events.append("low_information_turn")
        if turn_count == 1 and not signals.has_patient_segment:
            events.append("patient_segment_not_specified")
        if turn_count == 1 and not signals.has_permission:
            events.append("opening_missing_permission")

        if attitude == "skeptical" and not signals.has_evidence:
            events.append("evidence_not_addressed")
        if needs_evidence and signals.has_evidence and not signals.has_endpoint_detail:
            events.append("evidence_detail_missing")
        if needs_evidence and signals.has_evidence and signals.token_count > 25 and not (
            signals.has_patient_segment
            or signals.has_practical_relevance
            or signals.has_next_step
            or signals.has_question
        ):
            events.append("evidence_dump_without_use_case")
        if needs_evidence and signals.has_claim_language and not signals.has_evidence:
            events.append("unsupported_claim_without_evidence")
        if attitude == "concerned" or playbook_requires_safety:
            events.append("safety_first_context")
            if not signals.has_safety_signal:
                events.append("safety_reporting_not_started")
            if not signals.has_followup_process:
                events.append("followup_process_not_stated")
        if attitude == "dismissive" and not signals.has_practical_relevance:
            events.append("practical_relevance_not_established")
            if turn_count <= 2 and not signals.has_question:
                events.append("need_signal_not_established")
        if (attitude == "guarded" or playbook_requires_prior_context) and turn_count == 1:
            if not signals.acknowledges_prior_context:
                events.append("prior_rejection_not_acknowledged")
            if not signals.shows_new_relevance:
                events.append("no_new_relevance_after_rejection")
        if (decision_style == "system_constraint_driven" or playbook_requires_formulary) and turn_count <= 2 and not (
            signals.has_formulary_context or signals.has_question
        ):
            events.append("formulary_barrier_not_explored")
        if (decision_style == "system_constraint_driven" or playbook_requires_formulary) and signals.requests_large_commitment:
            events.append("unrealistic_adoption_request")
        if attitude == "cautious" and signals.requests_large_commitment:
            events.append("commitment_too_large_for_cautious_persona")
        if supports_competitor_reframe and turn_count <= 2 and not signals.has_question:
            events.append("decision_criteria_not_explored")
        if supports_competitor_reframe and signals.has_attack_comparison and not (
            signals.has_evidence and signals.has_uncertainty_language
        ):
            events.append("unsupported_competitor_comparison")
        if needs_discovery and turn_count <= 2 and not signals.has_question:
            events.append("weak_profiling_signal")
        if (
            "links_data_to_patient_segment" in heuristic_context.success_criteria
            or "fails_to_link_data_to_specific_patient_use" in heuristic_context.failure_patterns
            or attitude == "cautious"
        ) and signals.has_evidence and not signals.has_patient_segment:
            events.append("patient_use_case_not_defined")
        if turn_count >= closing_threshold and not signals.has_next_step:
            events.append("closing_next_step_missing")
        if (
            _needs_micro_commitment(heuristic_context=heuristic_context, persona=persona)
            and turn_count >= closing_threshold
            and signals.has_next_step
            and not signals.has_micro_commitment
        ):
            events.append("micro_commitment_missing")

        suggested_focus_subskills = {
            item
            for item in continuity_context.get("suggested_focus_subskills", [])
            if isinstance(item, str)
        }
        carryover_focus_subskills = {
            item
            for item in continuity_context.get("carryover_focus_subskills", [])
            if isinstance(item, str)
        }
        
        # Continuity-aware event injection
        if "opening" in carryover_focus_subskills and turn_count == 1 and signals.token_count > 25:
            events.append("carryover_opening_gap")
        if "profiling" in carryover_focus_subskills and turn_count <= 2 and not signals.has_question:
            events.append("carryover_profiling_gap")
        if "scientific_delivery" in carryover_focus_subskills and turn_count >= 2 and not signals.has_evidence:
            events.append("carryover_evidence_gap")
        if "closing_followup" in carryover_focus_subskills and turn_count >= closing_threshold and not signals.has_next_step:
            events.append("carryover_closing_gap")
        if turn_count == 1 and time_pressure == "high" and (
            signals.token_count > 25 or not signals.has_permission
        ):
            events.append("time_pressure_not_respected")
        if needs_discovery and turn_count <= 2 and not signals.has_question:
            events.append("carryover_need_discovery_gap")
        if turn_count <= 2 and needs_discovery and not signals.has_question:
            events.append("discovery_question_missing")
        if "scientific_delivery" in suggested_focus_subskills and attitude in {
            "skeptical",
            "cautious",
        } and not signals.has_evidence:
            events.append("carryover_evidence_gap")
        if "closing_followup" in suggested_focus_subskills and turn_count >= closing_threshold and not (
            signals.has_next_step
        ):
            events.append("carryover_followup_gap")
        if turn_count >= max_turns:
            events.append("max_turns_reached")

        should_finish = turn_count >= max_turns
        if should_finish:
            recommended_action = "finish_session"
        elif "safety_reporting_not_started" in events or "followup_process_not_stated" in events:
            recommended_action = "state_reporting_process_and_followup"
        elif "decision_criteria_not_explored" in events or "unsupported_competitor_comparison" in events:
            recommended_action = "ask_decision_criteria_before_comparison"
        elif "prior_rejection_not_acknowledged" in events or "no_new_relevance_after_rejection" in events:
            recommended_action = "acknowledge_prior_rejection_and_offer_update"
        elif "formulary_barrier_not_explored" in events:
            recommended_action = "ask_about_formulary_barrier"
        elif "commitment_too_large_for_cautious_persona" in events or "unrealistic_adoption_request" in events:
            recommended_action = "offer_low_risk_next_step"
        elif (
            phase == "closing"
            and (
                "closing_next_step_missing" in events
                or "carryover_followup_gap" in events
                or "micro_commitment_missing" in events
            )
        ):
            recommended_action = "state_micro_commitment_and_followup"
        elif (
            "evidence_not_addressed" in events
            or "carryover_evidence_gap" in events
            or "evidence_detail_missing" in events
            or "evidence_dump_without_use_case" in events
            or "unsupported_claim_without_evidence" in events
            or "patient_use_case_not_defined" in events
        ):
            recommended_action = "cite_endpoint_safety_and_patient_segment"
        elif "need_signal_not_established" in events:
            recommended_action = "reestablish_practical_need_before_pitch"
        elif (
            "weak_profiling_signal" in events
            or "discovery_question_missing" in events
            or "carryover_need_discovery_gap" in events
        ):
            recommended_action = "ask_one_targeted_discovery_question"
        elif (
            "opening_missing_permission" in events
            or "opening_overlong" in events
            or "time_pressure_not_respected" in events
            or "carryover_opening_gap" in events
        ):
            recommended_action = "shorten_opening_and_get_permission"
        elif "practical_relevance_not_established" in events or "patient_segment_not_specified" in events:
            recommended_action = "tie_message_to_current_patient_segment"
        elif (
            "closing_next_step_missing" in events
            or "carryover_followup_gap" in events
            or "micro_commitment_missing" in events
        ):
            recommended_action = "state_micro_commitment_and_followup"
        else:
            recommended_action = "continue"
        taxonomy_entries = director_taxonomy_entries(events)
        taxonomy_categories = director_taxonomy_categories(
            phase=phase,
            event_codes=events,
            recommended_action=recommended_action,
            should_finish=should_finish,
        )
        return DirectorDecision(
            phase=phase,
            events=events,
            should_finish=should_finish,
            recommended_action=recommended_action,
            taxonomy_categories=taxonomy_categories,
            taxonomy_entries=taxonomy_entries,
            turn_signals=signals,
        )

    def _doctor_reply(
        self,
        turn_count: int,
        user_message: str,
        decision: DirectorDecision,
        persona: dict[str, Any],
        continuity_context: dict[str, Any],
        scenario: ScenarioRecord | None = None,
        locale: str | None = None,
    ) -> str:
        locale_key = _reply_locale_key(locale)

        def reply(*, en: str, ja: str, zh: str) -> str:
            return _localized_text(locale_key=locale_key, en=en, ja=ja, zh=zh)

        response_style = persona.get("response_style", {}) if isinstance(persona, dict) else {}
        opening_line = response_style.get("likely_opening_line")
        signals = analyze_turn_message(user_message)
        suggested_focus_subskills = {
            item
            for item in continuity_context.get("suggested_focus_subskills", [])
            if isinstance(item, str)
        }
        attitude = str(persona.get("attitude", "neutral"))
        time_pressure = str(persona.get("time_pressure", ""))
        decision_style = str(persona.get("decision_style", ""))
        heuristic_context = _build_heuristic_context(continuity_context, scenario=scenario)
        prefers_early_close = _prefers_early_close(
            time_pressure=time_pressure,
            heuristic_context=heuristic_context,
        )
        playbook_question = _playbook_first_list_item(
            heuristic_context.playbook,
            "key_discovery_questions",
        )
        playbook_evidence_move = _playbook_first_list_item(
            heuristic_context.playbook,
            "acceptable_evidence_moves",
        )
        playbook_completion_signal = _playbook_first_list_item(
            heuristic_context.playbook,
            "completion_signals",
        )

        if "safety_reporting_not_started" in decision.events or "followup_process_not_stated" in decision.events:
            return reply(
                en=(
                    "Stop the promotion. Capture the event details, state the internal escalation "
                    "path, and tell me exactly what follow-up happens next."
                ),
                ja=(
                    "製品説明は止めてください。事象の詳細を記録し、院内の報告・連携経路を示し、"
                    "次に何をどうフォローするかを明確に伝えてください。"
                ),
                zh=(
                    "先停止推广内容。请记录不良事件细节，说明院内上报与升级路径，"
                    "并明确下一步具体随访动作。"
                ),
            )
        if "prior_rejection_not_acknowledged" in decision.events:
            return reply(
                en=(
                    "If you want another minute, first acknowledge the last discussion and tell me "
                    "what is genuinely different now."
                ),
                ja=(
                    "もう1分ほしいなら、まず前回の議論に触れて、"
                    "今回は何が本当に違うのかを示してください。"
                ),
                zh=(
                    "如果还想要我再给一分钟，请先承接上次讨论，"
                    "再说明这次到底有什么实质变化。"
                ),
            )
        if "no_new_relevance_after_rejection" in decision.events:
            return reply(
                en="Do not repeat the old message. Tell me what changed and why it matters now.",
                ja="前回と同じ話は繰り返さないでください。何が変わり、なぜ今重要なのかを示してください。",
                zh="不要重复旧信息。请说明到底变了什么，以及为什么现在重要。",
            )
        if (
            "decision_criteria_not_explored" in decision.events
            or "unsupported_competitor_comparison" in decision.events
        ):
            if playbook_question:
                return reply(
                    en=(
                        "Do not start with a competitor claim. Ask this first: "
                        f"{playbook_question}"
                    ),
                    ja=(
                        "競合比較から入らないでください。まずこの質問から始めてください："
                        f"{playbook_question}"
                    ),
                    zh=(
                        "不要先做竞品结论。请先问这个问题："
                        f"{playbook_question}"
                    ),
                )
            return reply(
                en=(
                    "Do not start with a competitor claim. Ask what decision criteria matter here, "
                    "then compare on that basis with factual support."
                ),
                ja=(
                    "競合比較から入らず、まず何を判断軸にしているかを確認し、"
                    "その軸に沿って事実ベースで比較してください。"
                ),
                zh=(
                    "不要先讲竞品结论。先确认对方的决策标准，再基于该标准做有事实依据的比较。"
                ),
            )
        if "formulary_barrier_not_explored" in decision.events:
            if playbook_question:
                return reply(
                    en=f"Before you detail further, ask this first: {playbook_question}",
                    ja=f"詳細に入る前に、まずこの質問をしてください：{playbook_question}",
                    zh=f"在继续展开前，请先问这个问题：{playbook_question}",
                )
            return reply(
                en=(
                    "Before you detail further, ask which formulary or pathway barrier is actually "
                    "blocking use, then suggest a realistic next step."
                ),
                ja=(
                    "説明を続ける前に、実際に採用を妨げているフォーミュラリー/運用上の障壁を確認し、"
                    "現実的な次の一手を示してください。"
                ),
                zh=(
                    "继续说明前，请先确认真正阻碍使用的是准入还是流程障碍，"
                    "再给出一个现实可行的下一步。"
                ),
            )
        if (
            "commitment_too_large_for_cautious_persona" in decision.events
            or "unrealistic_adoption_request" in decision.events
        ):
            return reply(
                en=(
                    "That step is too large. Link one evidence point to one patient segment and give "
                    "me a smaller, lower-risk next step."
                ),
                ja=(
                    "その提案は大きすぎます。エビデンス1点を患者像1つに結びつけ、"
                    "より小さく低リスクな次の一手にしてください。"
                ),
                zh=(
                    "这一步太大了。请把一个证据点对应到一个患者人群，"
                    "给出更小、更低风险的下一步。"
                ),
            )
        if (
            "evidence_detail_missing" in decision.events
            or "evidence_dump_without_use_case" in decision.events
            or "unsupported_claim_without_evidence" in decision.events
            or "patient_use_case_not_defined" in decision.events
            or "evidence_not_addressed" in decision.events
        ):
            if playbook_evidence_move:
                return reply(
                    en=(
                        "Be specific. Start with a supportable move like: "
                        f"{playbook_evidence_move} "
                        "Then give me the endpoint, the key safety context, and the patient "
                        "segment or use case this applies to. If the evidence is limited, say that plainly."
                    ),
                    ja=(
                        "具体的にお願いします。例えば次のような裏付け可能な提示から始めてください："
                        f"{playbook_evidence_move} "
                        "そのうえで、評価項目、安全性の要点、適用患者像（またはユースケース）を示してください。"
                        "根拠が限定的なら、その点も明確に述べてください。"
                    ),
                    zh=(
                        "请具体一点。可以先用这种可支撑的表达开场："
                        f"{playbook_evidence_move} "
                        "然后说明终点指标、安全性关键信息，以及适用患者人群（或使用场景）。"
                        "如果证据有限，也请直接说明。"
                    ),
                )
            return reply(
                en=(
                    "Be specific. Give me the endpoint, the key safety context, and the patient "
                    "segment or use case this applies to. If the evidence is limited, say that plainly."
                ),
                ja=(
                    "具体的に、評価項目・安全性の要点・適用患者像（またはユースケース）を示してください。"
                    "根拠が限定的なら、その点も率直に述べてください。"
                ),
                zh=(
                    "请具体说明终点指标、安全性关键信息，以及适用患者人群（或使用场景）。"
                    "如果证据有限，请直接讲清楚。"
                ),
            )
        if "need_signal_not_established" in decision.events:
            if playbook_question:
                return reply(
                    en=(
                        "You have not earned relevance yet. Ask this instead: "
                        f"{playbook_question}"
                    ),
                    ja=(
                        "まだ関連性を示せていません。代わりにこの質問をしてください："
                        f"{playbook_question}"
                    ),
                    zh=(
                        "你还没有建立相关性。请先问这个问题："
                        f"{playbook_question}"
                    ),
                )
            return reply(
                en=(
                    "You have not earned relevance yet. Tie this to a daily patient problem or ask "
                    "one concrete need question before you keep pitching."
                ),
                ja=(
                    "まだ関連性が不十分です。日常診療の患者課題に結びつけるか、"
                    "具体的なニーズ質問を1つしてから説明を続けてください。"
                ),
                zh=(
                    "目前相关性还不够。请先连接到日常患者问题，"
                    "或先问一个具体需求问题，再继续介绍。"
                ),
            )
        if turn_count == 1:
            if "opening" in suggested_focus_subskills and signals.token_count > 25:
                visit_window = reply(
                    en="30 seconds" if time_pressure == "high" else "one minute",
                    ja="30秒" if time_pressure == "high" else "1分",
                    zh="30秒" if time_pressure == "high" else "1分钟",
                )
                return reply(
                    en=(
                        f"You have {visit_window}. "
                        f"{_continuity_action_hint(continuity_context, 'opening', locale=locale_key)}"
                    ),
                    ja=(
                        f"使える時間は{visit_window}です。"
                        f"{_continuity_action_hint(continuity_context, 'opening', locale=locale_key)}"
                    ),
                    zh=(
                        f"你只有{visit_window}。"
                        f"{_continuity_action_hint(continuity_context, 'opening', locale=locale_key)}"
                    ),
                )
            if (
                _needs_discovery_signal(heuristic_context)
                and not signals.has_question
                and time_pressure != "high"
            ):
                if playbook_question:
                    return reply(
                        en=f"You are still talking at me. Ask this instead: {playbook_question}",
                        ja=f"まだ説明中心です。代わりにこの質問をしてください：{playbook_question}",
                        zh=f"你还在单向讲解。请改问这个问题：{playbook_question}",
                    )
                return _continuity_action_hint(
                    continuity_context,
                    "need_discovery",
                    locale=locale_key,
                )
            if (
                _needs_evidence_detail(
                    attitude=attitude,
                    decision_style=decision_style,
                    heuristic_context=heuristic_context,
                )
                and not signals.has_evidence
            ):
                return reply(
                    en=(
                        "Before we go further, give me the endpoint, safety context, and the patient "
                        "segment you mean."
                    ),
                    ja="先に進む前に、評価項目・安全性の文脈・対象患者像を示してください。",
                    zh="继续之前，请先说明终点指标、安全性背景和目标患者人群。",
                )
            if locale_key == "en" and isinstance(opening_line, str):
                return opening_line
        if decision.should_finish:
            if playbook_completion_signal:
                return reply(
                    en=(
                        "We are at the end. State one limited next step and the follow-up timing. "
                        f"Success here means: {playbook_completion_signal}"
                    ),
                    ja=(
                        "終了段階です。小さな次の一手を1つ示し、フォロー時期を明確にしてください。"
                        f"達成基準は次の通りです：{playbook_completion_signal}"
                    ),
                    zh=(
                        "现在进入收尾。请给出一个小而明确的下一步，并说明跟进时间。"
                        f"本轮成功标准是：{playbook_completion_signal}"
                    ),
                )
            if (
                "closing_followup" in suggested_focus_subskills
                or "closing_next_step_missing" in decision.events
                or "micro_commitment_missing" in decision.events
            ):
                return reply(
                    en=(
                        "We are at the end. State one limited next step, who owns it, and when you "
                        "will follow up."
                    ),
                    ja="終了段階です。小さな次の一手を1つ示し、担当者とフォロー時期を明確にしてください。",
                    zh="现在进入收尾。请给出一个小范围下一步，并明确负责人和跟进时间。",
                )
            return reply(
                en="We are at the end of this visit window. Please state your concrete next step.",
                ja="面談時間の終盤です。具体的な次の一手を示してください。",
                zh="本次会面已接近结束，请给出一个具体下一步。",
            )

        if "opening_missing_permission" in decision.events or "time_pressure_not_respected" in decision.events:
            visit_window = reply(
                en="30 seconds" if time_pressure == "high" else "one minute",
                ja="30秒" if time_pressure == "high" else "1分",
                zh="30秒" if time_pressure == "high" else "1分钟",
            )
            return reply(
                en=(
                    f"Keep this tighter. You have {visit_window}. "
                    f"{_continuity_action_hint(continuity_context, 'opening', locale=locale_key)}"
                ),
                ja=(
                    f"もっと簡潔にお願いします。使える時間は{visit_window}です。"
                    f"{_continuity_action_hint(continuity_context, 'opening', locale=locale_key)}"
                ),
                zh=(
                    f"请再精炼一些。你只有{visit_window}。"
                    f"{_continuity_action_hint(continuity_context, 'opening', locale=locale_key)}"
                ),
            )
        if "closing_next_step_missing" in decision.events or "micro_commitment_missing" in decision.events:
            if playbook_completion_signal:
                return reply(
                    en=(
                        "Before we end, give me one limited next step and the follow-up timing. "
                        f"Success here means: {playbook_completion_signal}"
                    ),
                    ja=(
                        "終える前に、小さな次の一手を1つ示し、フォロー時期を明確にしてください。"
                        f"達成基準は次の通りです：{playbook_completion_signal}"
                    ),
                    zh=(
                        "结束前，请给出一个小范围下一步，并说明跟进时间。"
                        f"本轮成功标准是：{playbook_completion_signal}"
                    ),
                )
            return reply(
                en=(
                    "Before we end, give me one limited next step for a defined patient or review, "
                    "and the follow-up timing."
                ),
                ja="終える前に、対象患者またはレビュー対象を限定した次の一手を1つ示し、フォロー時期を伝えてください。",
                zh="结束前，请给出一个面向明确患者或复查对象的小范围下一步，并说明跟进时间。",
            )
        if (
            _needs_discovery_signal(heuristic_context)
            and not signals.has_question
            and turn_count <= 2
        ):
            if playbook_question:
                return reply(
                    en=f"You are still talking at me. Ask this instead: {playbook_question}",
                    ja=f"まだ説明中心です。代わりにこの質問をしてください：{playbook_question}",
                    zh=f"你还在单向讲解。请改问这个问题：{playbook_question}",
                )
            return reply(
                en=(
                    "You are still talking at me. "
                    f"{_continuity_action_hint(continuity_context, 'need_discovery', locale=locale_key)}"
                ),
                ja=(
                    "まだ説明中心です。"
                    f"{_continuity_action_hint(continuity_context, 'need_discovery', locale=locale_key)}"
                ),
                zh=(
                    "你还在单向讲解。"
                    f"{_continuity_action_hint(continuity_context, 'need_discovery', locale=locale_key)}"
                ),
            )
        if (
            _needs_evidence_detail(
                attitude=attitude,
                decision_style=decision_style,
                heuristic_context=heuristic_context,
            )
            and (not signals.has_evidence or not signals.has_endpoint_detail)
        ):
            if playbook_evidence_move:
                return reply(
                    en=(
                        "That is still too vague. Start with a supportable move like: "
                        f"{playbook_evidence_move} "
                        "Then give me the endpoint, the key safety context, and the patient segment."
                    ),
                    ja=(
                        "まだ曖昧です。次のような裏付け可能な提示から始めてください："
                        f"{playbook_evidence_move} "
                        "そのうえで、評価項目・安全性の要点・対象患者像を示してください。"
                    ),
                    zh=(
                        "还是太笼统。请先用这种可支撑的表达开场："
                        f"{playbook_evidence_move} "
                        "然后给出终点指标、安全性关键信息和目标患者人群。"
                    ),
                )
            return reply(
                en=(
                    "That is still too vague. Give me the endpoint, the key safety context, and the "
                    "patient segment before you continue."
                ),
                ja="まだ曖昧です。続ける前に、評価項目・安全性の要点・対象患者像を示してください。",
                zh="还是太笼统。继续前请先说明终点指标、安全性关键信息和目标患者人群。",
            )
        if not signals.has_practical_relevance and attitude == "dismissive":
            return reply(
                en="Make this relevant to my daily patients or ask one useful need question before you continue.",
                ja="日常診療の患者にどう関係するかを示すか、有効なニーズ質問を1つしてから続けてください。",
                zh="请先说明这与我日常患者的关系，或先问一个有价值的需求问题再继续。",
            )
        if attitude == "skeptical":
            return reply(
                en="Please clarify the endpoint, safety context, and practical relevance.",
                ja="評価項目、安全性の文脈、実臨床での関連性を明確にしてください。",
                zh="请明确终点指标、安全性背景和临床实践相关性。",
            )
        if attitude == "dismissive":
            return reply(
                en="Keep this practical for my daily patients.",
                ja="日常診療の患者に役立つ実践的な話にしてください。",
                zh="请聚焦对我日常患者真正有用的实践信息。",
            )
        if attitude == "concerned":
            return reply(
                en="Before anything else, explain the reporting path and the exact follow-up process.",
                ja="まず最初に、報告経路と具体的なフォロー手順を説明してください。",
                zh="在其他内容之前，请先说明上报路径和具体随访流程。",
            )
        if attitude == "guarded":
            return reply(
                en="Be explicit about what changed since the last visit and why it matters now.",
                ja="前回訪問から何が変わり、なぜ今重要なのかを明確に示してください。",
                zh="请明确说明与上次拜访相比变了什么，以及为什么现在重要。",
            )
        if decision_style == "system_constraint_driven":
            return reply(
                en="Keep this realistic. Ask about the barrier and propose a step that fits the system.",
                ja="現実的に進めてください。障壁を確認し、運用に合う一手を提案してください。",
                zh="请保持现实可行。先问清障碍，再提出符合系统约束的一步。",
            )
        if prefers_early_close and turn_count >= 2:
            return reply(
                en="Keep this brief and land on one realistic next step.",
                ja="簡潔にまとめ、現実的な次の一手を1つに絞ってください。",
                zh="请简洁收束，落到一个现实可执行的下一步。",
            )
        return reply(
            en="Continue with one relevant patient segment, one proof point, and one realistic next step.",
            ja="関連する患者像1つ、根拠1点、現実的な次の一手1つで続けてください。",
            zh="请围绕一个相关患者人群、一个证据点和一个现实下一步继续。",
        )

    def _build_review(
        self,
        session: SessionRecord,
        scenario_focus_subskills: list[str],
        subskill_weights: dict[str, float],
        skill_model: dict[str, Any],
        diagnosis_types: dict[str, Any],
        compliance_rules: dict[str, Any],
        score_schema: dict[str, Any],
        judge_review_schema: dict[str, Any],
        coach_feedback_schema: dict[str, Any],
        compliance_flags_schema: dict[str, Any],
        model_artifact_generator: Any | None,
        session_context: DomainSessionContext,
    ) -> dict[str, Any]:
        def _merge_model_meta(
            current: dict[str, Any] | None,
            incoming: dict[str, Any] | None,
        ) -> dict[str, Any] | None:
            if not isinstance(incoming, dict) or not incoming:
                return current
            merged = dict(current or {})
            merged.update(incoming)
            return merged

        def _generic_model_error_meta(exc: Exception) -> dict[str, Any]:
            base_meta = dict(model_meta or {})
            base_meta.setdefault("fallback_target", "rule")
            base_meta.setdefault("failure_stage", "generator_exception")
            base_meta["error_type"] = type(exc).__name__
            detail = " ".join(str(exc).split()).strip()
            if detail:
                base_meta["error_detail"] = detail[:240]
            return base_meta

        turns_payload = [
            {
                "turn_index": turn.turn_index,
                "user_message": turn.user_message,
                "doctor_reply": turn.doctor_reply,
                "director_phase": turn.director_phase,
                "director_events": list(turn.director_events),
                "created_at": turn.created_at,
            }
            for turn in session.turns
        ]
        model_artifacts: dict[str, Any] | None = None
        model_error: str | None = None
        model_meta: dict[str, Any] | None = None
        if model_artifact_generator is not None:
            describe = getattr(model_artifact_generator, "describe", None)
            if callable(describe):
                described = describe()
                if isinstance(described, dict):
                    model_meta = dict(described)
            try:
                generated = model_artifact_generator.generate(
                    turns=turns_payload,
                    turn_count=session.turn_count,
                    scenario_focus_subskills=scenario_focus_subskills,
                    subskill_ids=list(subskill_weights.keys()),
                    prompt_context=session.prompt_context,
                )
                if isinstance(generated, dict):
                    model_artifacts = generated
                elif generated is not None:
                    model_error = "model_generator_returned_non_object"
            except ModelArtifactGenerationError as exc:
                model_error = str(exc)
                model_meta = _merge_model_meta(model_meta, exc.meta)
            except Exception as exc:
                model_error = str(exc)
                model_meta = _merge_model_meta(model_meta, _generic_model_error_meta(exc))

        return build_runtime_review(
            turns=turns_payload,
            turn_count=session.turn_count,
            finish_reason=session.finish_reason or "unknown",
            scenario_focus_subskills=scenario_focus_subskills,
            subskill_weights=subskill_weights,
            skill_model=skill_model,
            diagnosis_types=diagnosis_types,
            compliance_rules=compliance_rules,
            score_schema=score_schema,
            judge_review_schema=judge_review_schema,
            coach_feedback_schema=coach_feedback_schema,
            compliance_flags_schema=compliance_flags_schema,
            model_artifacts=model_artifacts,
            model_error=model_error,
            model_meta=model_meta,
            prompting_meta=summarize_prompt_context(session.prompt_context),
            session_context_meta=session_context.metadata_payload(),
            continuity_context=session.continuity_context,
        )

    def _persist_session(self, session: SessionRecord) -> None:
        if self._session_store is None:
            return
        self._session_store.upsert(session.session_id, self._serialize_session(session), org_id=session.context.org_id)

    def _load_session_from_store(self, session_id: str, *, org_id: str | None = None) -> SessionRecord | None:
        if self._session_store is None:
            return None
        payload = self._session_store.get(session_id, org_id=org_id)
        if payload is None:
            return None
        return self._deserialize_session(payload)

    def _append_event(self, session_id: str, event: dict[str, Any], *, org_id: str | None = None) -> None:
        if self._event_store is None:
            return
        self._event_store.append(session_id, event, org_id=org_id)

    def _serialize_session(self, session: SessionRecord) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "scenario_id": session.scenario_id,
            "learner_id": session.learner_id,
            "prompt_context": session.prompt_context,
            "continuity_context": session.continuity_context,
            "context": session.context.to_dict(),
            "status": session.status.value,
            "started_at": session.started_at,
            "updated_at": session.updated_at,
            "turn_count": session.turn_count,
            "finish_reason": session.finish_reason,
            "turns": [
                {
                    "turn_index": turn.turn_index,
                    "user_message": turn.user_message,
                    "doctor_reply": turn.doctor_reply,
                    "director_phase": turn.director_phase,
                    "director_events": list(turn.director_events),
                    "created_at": turn.created_at,
                }
                for turn in session.turns
            ],
            "review": session.review,
        }

    def _deserialize_session(self, payload: dict[str, Any]) -> SessionRecord:
        try:
            status = SessionStatus(str(payload["status"]))
            turns_payload = payload.get("turns", [])
            if not isinstance(turns_payload, list):
                raise ValueError("turns must be a list")
            turns = [
                TurnRecord(
                    turn_index=int(turn["turn_index"]),
                    user_message=str(turn["user_message"]),
                    doctor_reply=str(turn["doctor_reply"]),
                    director_phase=str(turn["director_phase"]),
                    director_events=list(turn.get("director_events", [])),
                    created_at=str(turn["created_at"]),
                )
                for turn in turns_payload
            ]
            review = payload.get("review")
            if review is not None and not isinstance(review, dict):
                raise ValueError("review must be an object")
            context_payload = payload.get("context")
            if context_payload is not None and not isinstance(context_payload, dict):
                raise ValueError("context must be an object")
            return SessionRecord(
                session_id=str(payload["session_id"]),
                scenario_id=str(payload["scenario_id"]),
                learner_id=str(payload["learner_id"]),
                prompt_context=_normalize_prompt_context(payload.get("prompt_context")),
                continuity_context=_normalize_continuity_context(payload.get("continuity_context")),
                context=(
                    DomainSessionContext.from_dict(context_payload)
                    if isinstance(context_payload, dict)
                    else DomainSessionContext.from_legacy_session_payload(payload)
                ),
                status=status,
                started_at=str(payload["started_at"]),
                updated_at=str(payload["updated_at"]),
                turn_count=int(payload.get("turn_count", len(turns))),
                finish_reason=payload.get("finish_reason"),
                turns=turns,
                review=review,
            )
        except Exception as exc:
            raise SessionTransitionError(f"Corrupted persisted session payload: {exc}") from exc

import hashlib
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from runtime_observability import (
    apply_response_trace_headers,
    bind_request_metadata,
    bind_session_context,
    emit_request_log,
    get_request_log_context,
    initialize_request_log_context,
)
from persistence.interfaces import EventStore
from persistence.store_factory import build_runtime_store_bundle
from providers import (
    build_model_artifact_generator,
    load_prompt_asset_bundle,
    load_runtime_prompt_context_from_env,
    summarize_prompt_context,
)
from providers.voice_provider import build_voice_provider
from runtime_context import DomainSessionContext
from runtime_config import (
    env_flag_enabled,
    resolve_demo_seed_mode,
    resolve_runtime_data_dir,
    should_seed_demo_runtime_data_on_boot,
)
from scenarios.asset_loader import DomainAssetError, get_domain_bundle
from services.audit_service import log_sensitive_access
from services.access_policy import (
    ALL_ARTIFACT_TYPES,
    AccessDecision,
    check_artifact_access,
    grant_admin_org_access,
    grant_learner_to_supervisor_access,
)
from services.coach_continuity import build_scenario_summary, build_session_continuity
from services.demo_progress_seed import ensure_demo_runtime_data
from services.training_plan_service import (
    TrainingPlan,
    TrainingPlanNotFoundError,
    TrainingPlanService,
)
from services.evaluation_gate_service import EvaluationGateService
from services.human_review_feedback import (
    HumanReviewFeedbackError,
    HumanReviewFeedbackService,
)
from services.organization_reports import (
    OrganizationReportAccessError,
    OrganizationReportService,
)
from services.progress_tracker import LearnerProgressNotFoundError, ProgressTracker
from session_engine.state_machine import (
    SessionEngine,
    SessionEvaluationError,
    SessionNotFoundError,
    SessionReviewUnavailableError,
    SessionStatus,
    SessionTransitionError,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Boot must fail fast if domain assets are invalid.
    bundle = get_domain_bundle()
    prompt_assets = load_prompt_asset_bundle()
    app.state.domain_bundle = bundle
    app.state.prompt_assets = prompt_assets
    data_dir = resolve_runtime_data_dir()
    store_bundle = build_runtime_store_bundle(data_dir)
    session_store = store_bundle.session_store
    event_store = store_bundle.event_store
    progress_store = store_bundle.progress_store
    requested_prompt_context = load_runtime_prompt_context_from_env()
    model_artifact_generator = build_model_artifact_generator()
    gate_service = EvaluationGateService(
        domain_bundle=bundle,
        session_store=session_store,
        requested_prompt_context=requested_prompt_context,
        allow_blocked_rollout=env_flag_enabled("MR_RUNTIME_ALLOW_BLOCKED_PROMPT_ROLLOUT", default=True),
    )
    prompt_context = gate_service.effective_prompt_context
    app.state.session_engine = SessionEngine(session_store=session_store, event_store=event_store)
    app.state.event_store = event_store
    app.state.session_store = session_store
    app.state.persistence_mode = store_bundle.mode
    app.state.sql_engine = store_bundle.sql_engine
    app.state.model_artifact_generator = model_artifact_generator
    app.state.default_prompt_context = prompt_context
    app.state.requested_prompt_context = requested_prompt_context
    app.state.evaluation_gate_service = gate_service
    app.state.demo_seed_mode = resolve_demo_seed_mode()
    app.state.progress_tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
        curriculum=bundle.curriculum,
        progress_store=progress_store,
    )
    app.state.organization_report_service = OrganizationReportService(
        session_store=session_store,
        scenario_catalog=bundle.scenarios,
        persona_catalog=bundle.personas,
    )
    app.state.human_review_feedback_service = HumanReviewFeedbackService(
        root_dir=data_dir / "human_review_feedback",
        session_store=session_store,
        domain_bundle=bundle,
    )
    if should_seed_demo_runtime_data_on_boot():
        ensure_demo_runtime_data(
            bundle=bundle,
            progress_tracker=app.state.progress_tracker,
            progress_store=progress_store,
            session_store=session_store,
            event_store=event_store,
            prompt_context=prompt_context,
        )
    app.state.voice_provider = build_voice_provider()
    app.state.training_plan_service = store_bundle.training_plan_service
    # In-memory sharing grant store for Alpha. Will be persisted in production.
    app.state.sharing_grants: dict[str, dict[str, Any]] = {}
    yield


app = FastAPI(title="mr-visit-jp-runtime", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def runtime_request_observability(request: Request, call_next):
    initialize_request_log_context(
        request,
        service_name="mr-visit-jp-runtime",
        domain_id="mr_visit_jp",
    )
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (perf_counter() - started_at) * 1000
        emit_request_log(request, status_code=500, duration_ms=duration_ms, error=exc)
        raise

    apply_response_trace_headers(response, request)
    duration_ms = (perf_counter() - started_at) * 1000
    emit_request_log(request, status_code=response.status_code, duration_ms=duration_ms)
    return response


def get_runtime_auth_mode() -> str:
    return os.getenv("MR_RUNTIME_AUTH_MODE", "disabled").strip().lower()


def _runtime_auth_enabled() -> bool:
    return get_runtime_auth_mode() != "disabled"


def _normalize_header_value(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def get_org_id(request: Request) -> str | None:
    return _normalize_header_value(request.headers.get("X-Org-ID"))


def get_viewer_role(request: Request) -> str | None:
    role = _normalize_header_value(request.headers.get("X-Viewer-Role"))
    return role.lower() if role else None


def get_auth_user(request: Request) -> str | None:
    return _normalize_header_value(request.headers.get("X-Auth-User"))


LEARNER_DATA_ROLES = frozenset({
    "supervisor",
    "organization_admin",
    "platform_admin",
})
ORGANIZATION_REPORT_ROLES = LEARNER_DATA_ROLES
ADMIN_OPERATION_ROLES = frozenset({
    "organization_admin",
    "content_admin",
    "platform_admin",
})


def _role_allowed(request: Request, allowed_roles: frozenset[str]) -> bool:
    viewer_role = get_viewer_role(request)
    return bool(viewer_role and viewer_role in allowed_roles)


def _enforce_learner_access(request: Request, learner_id: str) -> None:
    if not _runtime_auth_enabled():
        return
    auth_user = get_auth_user(request)
    if not auth_user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Set X-Auth-User header.",
        )
    if auth_user == learner_id or _role_allowed(request, LEARNER_DATA_ROLES):
        return
    raise HTTPException(
        status_code=403,
        detail="Learners can only access their own training data.",
    )


def _enforce_session_access(request: Request, session: Any) -> None:
    learner_id = getattr(session, "learner_id", "")
    _enforce_learner_access(request, str(learner_id))


def _enforce_organization_report_access(request: Request) -> None:
    if not _runtime_auth_enabled():
        return
    if _role_allowed(request, ORGANIZATION_REPORT_ROLES):
        return
    raise HTTPException(
        status_code=403,
        detail="Organization reports require supervisor or administrator access.",
    )


def _enforce_admin_operation_access(request: Request) -> None:
    if not _runtime_auth_enabled():
        return
    if _role_allowed(request, ADMIN_OPERATION_ROLES):
        return
    raise HTTPException(
        status_code=403,
        detail="Admin operations require an administrator role.",
    )


_PUBLIC_ENDPOINTS = frozenset({
    "/healthz",
    "/_local/diagnostics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/v1/scenarios",
})


@app.middleware("http")
async def runtime_auth_check(request: Request, call_next):
    if _runtime_auth_enabled():
        path = request.url.path.rstrip("/") or "/"
        if path not in _PUBLIC_ENDPOINTS:
            auth_user = get_auth_user(request)
            if not auth_user:
                return JSONResponse(
                    {"detail": "Authentication required. Set X-Auth-User header."},
                    status_code=401,
                )
            org_id = get_org_id(request)
            if not org_id:
                return JSONResponse(
                    {"detail": "Organization context required. Set X-Org-ID header."},
                    status_code=401,
                )
    response = await call_next(request)
    return response


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


DEFAULT_SESSION_LOCALE = "en-US"


def _normalize_start_session_locale(value: str | None) -> str:
    if not isinstance(value, str):
        return DEFAULT_SESSION_LOCALE
    normalized = value.strip()
    if not normalized:
        return DEFAULT_SESSION_LOCALE
    lowered = normalized.lower()
    if lowered.startswith("ja"):
        return "ja-JP"
    if lowered.startswith("zh"):
        return "zh-CN"
    if lowered.startswith("en"):
        return "en-US"
    return normalized


class StartSessionRequest(BaseModel):
    scenario_id: str
    learner_id: str
    locale: str | None = None


class SendTurnRequest(BaseModel):
    message: str = Field(min_length=1)
    persona_id: str | None = None


class ScenarioSummary(BaseModel):
    id: str
    title: str
    difficulty: str
    focus_subskills: list[str]
    doctor_persona_id: str
    persona_label: str
    persona_attitude: str
    persona_time_pressure: str
    persona_specialty: str
    max_turns: int
    success_criteria: list[str]
    failure_patterns: list[str]


class RuntimeHealthResponse(BaseModel):
    status: str
    domain_id: str
    scenario_count: int
    prompt_profile: str
    experiment_id: str | None = None
    persistence_mode: str | None = None
    demo_seed_mode: str | None = None


class ScenarioListResponse(BaseModel):
    domain_id: str
    scenario_count: int
    scenarios: list[ScenarioSummary]


class StartSessionResponse(BaseModel):
    session_id: str
    scenario_id: str
    learner_id: str
    status: str
    scenario: ScenarioSummary
    coach_continuity: dict[str, Any]
    experiment_context: dict[str, Any]


class DirectorPayload(BaseModel):
    phase: str
    events: list[str]
    should_finish: bool
    recommended_action: str


class SendTurnResponse(BaseModel):
    session_id: str
    status: str
    turn_index: int
    doctor_reply: str
    persona_id: str | None = None
    director: DirectorPayload


class TurnSnapshotResponse(BaseModel):
    turn_index: int
    user_message: str
    doctor_reply: str
    director_phase: str
    director_events: list[str]
    created_at: str
    persona_id: str | None = None


class GetSessionResponse(BaseModel):
    session_id: str
    scenario_id: str
    learner_id: str
    status: str
    turn_count: int
    started_at: str
    updated_at: str
    scenario: ScenarioSummary
    coach_continuity: dict[str, Any]
    turns: list[TurnSnapshotResponse]
    experiment_context: dict[str, Any]


class FinishSessionResponse(BaseModel):
    session_id: str
    scenario_id: str
    learner_id: str
    status: str
    finish_reason: str
    review: dict[str, Any]
    coach_continuity: dict[str, Any]
    progress_snapshot: dict[str, Any]
    experiment_context: dict[str, Any]


class GetReviewResponse(BaseModel):
    session_id: str
    scenario_id: str
    learner_id: str
    status: str
    finish_reason: str
    turn_count: int
    started_at: str
    updated_at: str
    scenario: ScenarioSummary
    review: dict[str, Any]
    coach_continuity: dict[str, Any] | None = None
    coach_memory: dict[str, Any] | None = None
    experiment_context: dict[str, Any]


class SessionSummaryResponse(BaseModel):
    """Redacted session summary for supervisor views (no transcript data)."""
    session_id: str
    scenario_id: str
    learner_hash: str | None = None
    status: str
    finish_reason: str | None = None
    turn_count: int
    overall_score: int | None = None
    overall_band: str | None = None
    priority_subskills: list[str] = []
    max_compliance_severity: str | None = None
    started_at: str
    updated_at: str
    review_ready: bool = False
    detail: str = "Transcript content restricted for supervisor view. Use organization reports for aggregate metrics."


class ScenarioRecommendationResponse(BaseModel):
    scenario_id: str
    title: str
    difficulty: str
    target_subskills: list[str]
    reason: str
    recommendation_type: str = "skill"
    evidence_source: str | None = None
    stop_condition: str | None = None
    expected_difficulty: str | None = None
    suggested_repetition_count: int = 1
    reason_category: str = "skill"


class PracticePathEntryResponse(ScenarioRecommendationResponse):
    step_index: int


class WeaknessClusterResponse(BaseModel):
    cluster_id: str
    subskills: list[str]
    occurrences: int
    last_seen_at: str


class CurriculumScenarioProgressResponse(BaseModel):
    scenario_id: str
    title: str
    attempt_count: int
    required: bool
    remaining_repetitions: int


class CurriculumProgressMetricsResponse(BaseModel):
    completed_sessions: int
    required_scenarios_completed: int
    required_scenarios_total: int
    average_stage_score: float
    target_subskill_average: float


class CurriculumProgressResponse(BaseModel):
    curriculum_id: str
    curriculum_title: str
    current_stage_id: str
    current_stage_title: str
    current_stage_description: str
    current_module_id: str
    current_module_title: str
    stage_position: int
    total_stages: int
    status: str
    mastery_status: str
    review_status: str
    next_review_in_sessions: int | None = None
    target_subskills: list[str]
    recommended_repetition: int
    current_stage_scenarios: list[CurriculumScenarioProgressResponse]
    completed_stage_ids: list[str]
    rationale: str
    next_stage_id: str | None = None
    next_stage_title: str | None = None
    attention_reason: str
    metrics: CurriculumProgressMetricsResponse


class GetProgressSnapshotResponse(BaseModel):
    learner_id: str
    total_sessions: int
    total_exp: int
    level: int
    updated_at: str
    latest_recommendations: list[ScenarioRecommendationResponse]
    practice_path: list[PracticePathEntryResponse]
    weakness_clusters: list[WeaknessClusterResponse]
    subskills: dict[str, Any]
    recent_history: list[dict[str, Any]]
    coach_memory: dict[str, Any]
    curriculum: CurriculumProgressResponse
    skill_world: dict[str, Any]
    performance_analytics: dict[str, Any]


class GetSessionEventsResponse(BaseModel):
    session_id: str
    event_count: int
    events: list[dict[str, Any]]


class OrganizationWeaknessResponse(BaseModel):
    subskill_id: str
    occurrences: int
    affected_learners: int


class AttentionReasonResponse(BaseModel):
    code: str
    detail: str
    subskill_id: str | None = None
    severity: str | None = None


class OrganizationReviewSummaryResponse(BaseModel):
    session_id: str
    learner_id: str
    scenario_id: str
    scenario_title: str
    persona_label: str | None = None
    status: str
    started_at: str
    updated_at: str
    finish_reason: str | None = None
    overall_score: int | None = None
    overall_band: str | None = None
    prompt_profile: str | None = None
    max_compliance_severity: str | None = None
    priority_subskills: list[str]
    review_ready: bool


class LearnerOrganizationSummaryResponse(BaseModel):
    learner_id: str
    learner_hash: str | None = None
    total_sessions: int
    finalized_sessions: int
    active_sessions: int
    average_score: float | None = None
    last_score: int | None = None
    practice_completion_rate: float
    highest_compliance_severity: str | None = None
    recurring_weaknesses: list[OrganizationWeaknessResponse]
    active_focus_subskills: list[str]
    needs_attention: bool
    needs_attention_reasons: list[AttentionReasonResponse]
    latest_session_at: str | None = None
    latest_scenario_title: str | None = None
    recent_reviews: list[OrganizationReviewSummaryResponse]


class TeamSummaryResponse(BaseModel):
    learner_count: int
    total_sessions: int
    finalized_sessions: int
    active_sessions: int
    average_score: float | None = None
    practice_completion_rate: float
    compliance_risk_session_count: int
    high_risk_session_count: int
    at_risk_learner_count: int
    recurring_weaknesses: list[OrganizationWeaknessResponse]
    latest_activity_at: str | None = None


class GetOrganizationReportsResponse(BaseModel):
    organization_id: str
    organization_scope: str
    generated_at: str
    team_summary: TeamSummaryResponse
    learners: list[LearnerOrganizationSummaryResponse]


class PromptContextSummaryResponse(BaseModel):
    profile_id: str
    experiment_id: str | None = None
    flags: list[str]
    contracts: dict[str, Any]


class EvaluationGateCheckResponse(BaseModel):
    name: str
    passed: bool
    detail: str


class OfflineFixtureResultResponse(BaseModel):
    fixture_name: str
    fixture_path: str
    bucket: str
    scenario_ids: list[str]
    focus_subskills: list[str]
    finish_reason: str
    compliance_case: str
    tags: list[str]
    passed: bool
    overall_score: int
    overall_band: str


class CoverageDimensionResponse(BaseModel):
    covered: list[str]
    missing: list[str]
    counts: dict[str, int]


class TrainingPlanRequest(BaseModel):
    plan_id: str | None = None
    org_id: str = "default"
    title: str
    description: str = ""
    owner_id: str = ""
    assigned_learners: list[str] = []
    assigned_cohorts: list[str] = []
    target_subskills: list[str] = []
    required_scenario_ids: list[str] = []
    due_date: str | None = None
    goal_criteria: str = ""
    success_threshold: float = 4.0
    review_cadence: str = "after_each_session"
    status: str = "active"


class TrainingPlanResponse(BaseModel):
    plan_id: str
    org_id: str
    title: str
    description: str
    owner_id: str
    assigned_learners: list[str]
    assigned_cohorts: list[str]
    target_subskills: list[str]
    required_scenario_ids: list[str]
    due_date: str | None = None
    goal_criteria: str
    success_threshold: float
    review_cadence: str
    status: str
    created_at: str
    updated_at: str
    version: int


class TrainingPlanListResponse(BaseModel):
    plan_count: int
    plans: list[TrainingPlanResponse]


class AssignLearnersRequest(BaseModel):
    learner_ids: list[str]


class SharingGrantRequest(BaseModel):
    """Create a sharing grant for a learner to share access with a supervisor."""
    grantee_role: str = "supervisor"
    grantee_scope: str          # "user:<id>" | "org:<id>"
    artifact_types: list[str] | None = None
    reason: str = ""
    expires_at: str | None = None


class SharingGrantResponse(BaseModel):
    grant_id: str
    granter_id: str
    granter_org_id: str
    grantee_role: str
    grantee_scope: str
    artifact_types: list[str]
    reason: str
    expires_at: str | None = None
    created_at: str


class SharingGrantListResponse(BaseModel):
    grants: list[SharingGrantResponse]


class UnassignLearnersRequest(BaseModel):
    learner_ids: list[str]


class OfflineDatasetCoverageResponse(BaseModel):
    scenarios: CoverageDimensionResponse
    subskills: CoverageDimensionResponse
    compliance_cases: CoverageDimensionResponse
    finish_reasons: CoverageDimensionResponse


class OfflineDatasetSummaryResponse(BaseModel):
    fixture_schema_version: int
    fixture_count: int
    fixtures_by_bucket: dict[str, int]
    coverage: OfflineDatasetCoverageResponse


class OfflineEvaluationGateResponse(BaseModel):
    profile_id: str
    status: str
    fixture_pass_rate: float
    fixture_results: list[OfflineFixtureResultResponse]
    contract_versions: dict[str, int]
    output_requirement_counts: dict[str, int]
    checks: list[EvaluationGateCheckResponse]


class OnlineEvaluationGateResponse(BaseModel):
    profile_id: str
    experiment_id: str | None = None
    status: str
    sample_size: int
    metrics: dict[str, Any]
    thresholds: dict[str, Any]
    checks: list[EvaluationGateCheckResponse]
    updated_at: str


class PromptRolloutDecisionResponse(BaseModel):
    status: str
    requested: PromptContextSummaryResponse
    effective: PromptContextSummaryResponse
    stable_profile_id: str
    allow_blocked_rollout: bool
    checks: list[EvaluationGateCheckResponse]


class GetEvaluationGatesResponse(BaseModel):
    domain_id: str
    default_profile_id: str
    rollout: PromptRolloutDecisionResponse
    offline_dataset: OfflineDatasetSummaryResponse
    offline_gates: list[OfflineEvaluationGateResponse]
    online_gates: list[OnlineEvaluationGateResponse]


class HumanReviewRecordCreateRequest(BaseModel):
    session_id: str
    reviewer_id: str
    reviewer_role: str = "sme"
    verdict: str
    record_id: str | None = None
    supersedes_version: int | None = None
    sme_comment: str | None = None
    subskill_score_overrides: dict[str, int] = Field(default_factory=dict)
    diagnosis_add_ids: list[str] = Field(default_factory=list)
    diagnosis_remove_ids: list[str] = Field(default_factory=list)
    compliance_severity_overrides: list[dict[str, str]] = Field(default_factory=list)
    evidence_sufficiency: dict[str, bool] = Field(default_factory=dict)
    fixture_promotion: dict[str, Any] = Field(default_factory=dict)


class HumanReviewRecordEnvelopeResponse(BaseModel):
    record: dict[str, Any]


class HumanReviewRecordListResponse(BaseModel):
    record_count: int
    records: list[dict[str, Any]]


class HumanReviewImportRequest(BaseModel):
    bundle: dict[str, Any]


class HumanReviewImportResponse(BaseModel):
    summary: dict[str, Any]


class HumanReviewExportResponse(BaseModel):
    bundle: dict[str, Any]


class HumanReviewFixtureCandidatesResponse(BaseModel):
    payload: dict[str, Any]


def _hash_identifier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def _session_turn_count(payload: dict[str, Any]) -> int:
    turn_count = payload.get("turn_count")
    if isinstance(turn_count, int):
        return max(turn_count, 0)
    turns = payload.get("turns")
    if isinstance(turns, list):
        return len(turns)
    return 0


def _session_overall_score(payload: dict[str, Any]) -> int | None:
    review = payload.get("review")
    if not isinstance(review, dict):
        return None
    overall_score = review.get("overall_score")
    if isinstance(overall_score, int):
        return overall_score
    return None


def _recent_session_summary(payload: dict[str, Any]) -> dict[str, Any]:
    learner_id = str(payload.get("learner_id", "")).strip()
    prompt_context = summarize_prompt_context(payload.get("prompt_context"))
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    trace_id = context.get("trace_id")
    return {
        "session_id": str(payload.get("session_id", "")).strip(),
        "learner_id": learner_id,
        "learner_hash": _hash_identifier(learner_id),
        "scenario_id": str(payload.get("scenario_id", "")).strip(),
        "status": str(payload.get("status", "")).strip() or "unknown",
        "turn_count": _session_turn_count(payload),
        "updated_at": str(payload.get("updated_at", "")).strip(),
        "finish_reason": str(payload.get("finish_reason", "")).strip() or None,
        "prompt_profile": prompt_context.get("profile_id"),
        "experiment_id": prompt_context.get("experiment_id"),
        "trace_id": str(trace_id).strip() if isinstance(trace_id, str) and trace_id.strip() else None,
        "overall_score": _session_overall_score(payload),
    }


def _runtime_diagnostics_payload() -> dict[str, Any]:
    bundle = app.state.domain_bundle
    gate_service: EvaluationGateService = app.state.evaluation_gate_service
    human_review_feedback_service: HumanReviewFeedbackService = app.state.human_review_feedback_service
    session_payloads = app.state.session_store.list_all()
    session_counts = {
        "total": len(session_payloads),
        "active": 0,
        "running": 0,
        "awaiting_finish": 0,
        "finalized": 0,
        "other": 0,
    }
    for payload in session_payloads:
        status = str(payload.get("status", "")).strip()
        if status == "running":
            session_counts["running"] += 1
            session_counts["active"] += 1
        elif status == "awaiting_finish":
            session_counts["awaiting_finish"] += 1
            session_counts["active"] += 1
        elif status == "finalized":
            session_counts["finalized"] += 1
        else:
            session_counts["other"] += 1

    recent_sessions = sorted(
        (_recent_session_summary(payload) for payload in session_payloads),
        key=lambda item: (str(item.get("updated_at", "")), str(item.get("session_id", ""))),
        reverse=True,
    )[:5]
    human_review_records = human_review_feedback_service.list_records()
    latest_record_ids = {
        str(item.get("record_id", ""))
        for item in human_review_records
        if isinstance(item, dict)
    }
    return {
        "status": "ok",
        "service_name": "mr-visit-jp-runtime",
        "domain_id": bundle.manifest["id"],
        "scenario_count": len(bundle.scenarios),
        "persistence_mode": app.state.persistence_mode,
        "demo_seed_mode": app.state.demo_seed_mode,
        "prompt_context": summarize_prompt_context(gate_service.effective_prompt_context),
        "requested_prompt_context": summarize_prompt_context(app.state.requested_prompt_context),
        "session_counts": session_counts,
        "human_review_feedback": {
            "record_count": len(human_review_records),
            "active_record_count": len(latest_record_ids),
        },
        "recent_sessions": recent_sessions,
    }


def _scenario_response(scenario: Any, persona: dict[str, Any]) -> ScenarioSummary:
    return ScenarioSummary(**build_scenario_summary(scenario, persona))


def _enforce_supervisor_transcript_policy(
    request: Request,
    *,
    learner_id: str | None = None,
) -> None:
    viewer_role = get_viewer_role(request)
    if viewer_role != "supervisor":
        return
    auth_user = get_auth_user(request)
    is_own_data = bool(auth_user and learner_id and auth_user == learner_id)
    decision = check_artifact_access(
        viewer_role,
        "transcript_text",
        is_own_data=is_own_data,
        is_same_org=True,
    )
    if not decision.allowed and viewer_role == "supervisor" and is_own_data:
        # Supervisors running their own learner sessions should be able to
        # read transcript artifacts for that self-owned data.
        return
    if not decision.allowed:
        raise HTTPException(
            status_code=403,
            detail="Supervisor view cannot access raw session transcripts. "
                   "Use organization reports (/v1/organizations/{org_id}/reports) "
                   "for authorized aggregate and summary views.",
        )


def _enforce_artifact_access(
    request: Request,
    artifact_type: str,
    *,
    is_own_data: bool = False,
    is_same_org: bool = True,
) -> AccessDecision:
    """Centralized access check using the policy module.

    Returns the AccessDecision. Raises HTTPException(403) if denied.
    """
    if not _runtime_auth_enabled():
        return AccessDecision(allowed=True, reason="Auth disabled; access granted.", effective_level="org")

    viewer_role = get_viewer_role(request)
    decision = check_artifact_access(
        viewer_role,
        artifact_type,
        is_own_data=is_own_data,
        is_same_org=is_same_org,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=403,
            detail=decision.reason,
        )
    return decision


@app.get("/healthz", response_model=RuntimeHealthResponse)
def healthz(request: Request) -> RuntimeHealthResponse:
    bundle = get_domain_bundle()
    prompt_context = summarize_prompt_context(app.state.default_prompt_context)
    bind_request_metadata(
        request,
        action_id="healthz",
        domain_id=bundle.manifest["id"],
        prompt_profile=prompt_context["profile_id"],
        experiment_id=prompt_context.get("experiment_id"),
    )
    return RuntimeHealthResponse(
        status="ok",
        domain_id=bundle.manifest["id"],
        scenario_count=len(bundle.scenarios),
        persistence_mode=app.state.persistence_mode,
        demo_seed_mode=app.state.demo_seed_mode,
        prompt_profile=prompt_context["profile_id"],
        experiment_id=prompt_context.get("experiment_id"),
    )


@app.get("/_local/diagnostics")
def local_diagnostics(request: Request) -> dict[str, Any]:
    diagnostics = _runtime_diagnostics_payload()
    prompt_context = diagnostics["prompt_context"]
    bind_request_metadata(
        request,
        action_id="local_diagnostics",
        domain_id=diagnostics["domain_id"],
        prompt_profile=prompt_context["profile_id"],
        experiment_id=prompt_context.get("experiment_id"),
    )
    return diagnostics


@app.post(
    "/_local/human-review-feedback/records",
    response_model=HumanReviewRecordEnvelopeResponse,
)
def create_human_review_feedback_record(
    request: Request,
    payload: HumanReviewRecordCreateRequest,
) -> HumanReviewRecordEnvelopeResponse:
    bind_request_metadata(
        request,
        action_id="create_human_review_feedback_record",
        session_id=payload.session_id,
    )
    service: HumanReviewFeedbackService = app.state.human_review_feedback_service
    org_id = get_org_id(request)
    try:
        record = service.create_record(payload.model_dump(), org_id=org_id)
    except HumanReviewFeedbackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HumanReviewRecordEnvelopeResponse(record=record)


@app.get(
    "/_local/human-review-feedback/records",
    response_model=HumanReviewRecordListResponse,
)
def list_human_review_feedback_records(
    request: Request,
    session_id: str | None = None,
    latest_only: bool = False,
) -> HumanReviewRecordListResponse:
    bind_request_metadata(request, action_id="list_human_review_feedback_records")
    service: HumanReviewFeedbackService = app.state.human_review_feedback_service
    org_id = get_org_id(request)
    try:
        records = service.list_records(
            org_id=org_id,
            session_id=session_id,
            latest_only=latest_only,
        )
    except HumanReviewFeedbackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HumanReviewRecordListResponse(record_count=len(records), records=records)


@app.get(
    "/_local/human-review-feedback/export",
    response_model=HumanReviewExportResponse,
)
def export_human_review_feedback_records(
    request: Request,
    session_id: str | None = None,
    latest_only: bool = False,
) -> HumanReviewExportResponse:
    bind_request_metadata(request, action_id="export_human_review_feedback_records")
    service: HumanReviewFeedbackService = app.state.human_review_feedback_service
    org_id = get_org_id(request)
    try:
        bundle = service.export_bundle(
            org_id=org_id,
            session_id=session_id,
            latest_only=latest_only,
        )
    except HumanReviewFeedbackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HumanReviewExportResponse(bundle=bundle)


@app.post(
    "/_local/human-review-feedback/import",
    response_model=HumanReviewImportResponse,
)
def import_human_review_feedback_records(
    request: Request,
    payload: HumanReviewImportRequest,
) -> HumanReviewImportResponse:
    bind_request_metadata(request, action_id="import_human_review_feedback_records")
    service: HumanReviewFeedbackService = app.state.human_review_feedback_service
    org_id = get_org_id(request)
    try:
        summary = service.import_bundle(payload.bundle, org_id=org_id)
    except HumanReviewFeedbackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HumanReviewImportResponse(summary=summary)


@app.get(
    "/_local/human-review-feedback/fixture-candidates",
    response_model=HumanReviewFixtureCandidatesResponse,
)
def list_human_review_feedback_fixture_candidates(
    request: Request,
    latest_only: bool = True,
) -> HumanReviewFixtureCandidatesResponse:
    bind_request_metadata(request, action_id="list_human_review_feedback_fixture_candidates")
    service: HumanReviewFeedbackService = app.state.human_review_feedback_service
    org_id = get_org_id(request)
    try:
        payload = service.build_fixture_candidates(
            org_id=org_id,
            latest_only=latest_only,
        )
    except HumanReviewFeedbackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HumanReviewFixtureCandidatesResponse(payload=payload)


@app.get("/v1/scenarios", response_model=ScenarioListResponse)
def list_scenarios(request: Request) -> ScenarioListResponse:
    prompt_context = summarize_prompt_context(app.state.default_prompt_context)
    bind_request_metadata(
        request,
        action_id="list_scenarios",
        prompt_profile=prompt_context["profile_id"],
        experiment_id=prompt_context.get("experiment_id"),
    )
    bundle = get_domain_bundle()
    scenario_summaries = [
        _scenario_response(scenario, bundle.personas[scenario.doctor_persona_id])
        for scenario in bundle.scenarios.values()
    ]
    return ScenarioListResponse(
        domain_id=bundle.manifest["id"],
        scenario_count=len(scenario_summaries),
        scenarios=scenario_summaries,
    )


@app.post("/v1/sessions/start", response_model=StartSessionResponse)
def start_session(request: Request, payload: StartSessionRequest) -> StartSessionResponse:
    bind_request_metadata(
        request,
        action_id="start_session",
        learner_id=payload.learner_id,
    )
    _enforce_learner_access(request, payload.learner_id)
    try:
        bundle = get_domain_bundle()
    except DomainAssetError as exc:  # pragma: no cover - startup should already fail
        raise HTTPException(status_code=500, detail=f"Domain assets unavailable: {exc}") from exc

    if payload.scenario_id not in bundle.scenarios:
        raise HTTPException(status_code=404, detail=f"Unknown scenario_id: {payload.scenario_id}")

    session_id = f"sess_{uuid4().hex[:12]}"
    session_engine: SessionEngine = app.state.session_engine
    progress_tracker: ProgressTracker = app.state.progress_tracker
    prompt_context = app.state.default_prompt_context
    bind_request_metadata(
        request,
        prompt_profile=prompt_context["profile_id"],
        experiment_id=prompt_context.get("experiment_id"),
    )
    org_id = get_org_id(request)
    session_locale = _normalize_start_session_locale(payload.locale)
    scenario = bundle.scenarios[payload.scenario_id]
    persona = bundle.personas[scenario.doctor_persona_id]
    try:
        progress_snapshot = progress_tracker.get_snapshot(payload.learner_id, org_id=org_id)
        coach_memory = (
            progress_snapshot.get("coach_memory", {})
            if isinstance(progress_snapshot, dict)
            else {}
        )
    except LearnerProgressNotFoundError:
        coach_memory = {}
    session_started_at = _utc_now_iso()
    # Load active training plans for this learner
    active_training_plan: dict[str, Any] | None = None
    training_plan_service: TrainingPlanService | None = app.state.training_plan_service
    if training_plan_service is not None:
        try:
            active_plans = training_plan_service.get_active_plans_for_learner(
                payload.learner_id, org_id=org_id
            )
            if active_plans:
                active_training_plan = active_plans[0].to_dict()
        except Exception:
            pass  # Non-critical: session can start without plan context
    if active_training_plan:
        required_ids = active_training_plan.get("required_scenario_ids") or []
        if required_ids and payload.scenario_id not in required_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Scenario '{payload.scenario_id}' is not allowed by your active training plan. "
                       f"Required scenarios: {', '.join(required_ids)}",
            )
    coach_continuity = build_session_continuity(
        coach_memory=coach_memory,
        scenario=scenario,
        persona=persona,
        session_id=session_id,
        started_at=session_started_at,
        active_training_plan=active_training_plan,
    )
    session_context = DomainSessionContext.from_session_seed(
        skill_id=str(bundle.manifest.get("id", "mr_visit_jp")),
        session_id=session_id,
        learner_id=payload.learner_id,
        scenario_id=payload.scenario_id,
        persona_id=scenario.doctor_persona_id,
        prompt_context=prompt_context,
        continuity_context=coach_continuity,
        locale=session_locale,
        trace_id=get_request_log_context(request).trace_id,
        org_id=org_id,
    )
    bind_session_context(request, session_context)
    session_engine.create_session(
        session_id=session_id,
        scenario_id=payload.scenario_id,
        learner_id=payload.learner_id,
        prompt_context=prompt_context,
        continuity_context=coach_continuity,
        context=session_context,
        started_at=session_started_at,
    )

    return StartSessionResponse(
        session_id=session_id,
        scenario_id=payload.scenario_id,
        learner_id=payload.learner_id,
        status="initialized",
        scenario=_scenario_response(scenario, persona),
        coach_continuity=coach_continuity,
        experiment_context=summarize_prompt_context(prompt_context),
    )


@app.get("/v1/sessions/{session_id}", response_model=GetSessionResponse)
def get_session(request: Request, session_id: str) -> GetSessionResponse:
    org_id = get_org_id(request)
    bind_request_metadata(request, action_id="get_session", session_id=session_id)
    session_engine: SessionEngine = app.state.session_engine
    try:
        session = session_engine.get_session(session_id, org_id=org_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        _enforce_supervisor_transcript_policy(request, learner_id=session.learner_id)
    except HTTPException:
        log_sensitive_access(
            request,
            action="transcript.read",
            target_type="session",
            target_id=session_id,
            learner_id=session.learner_id,
            result="denied",
            detail="Supervisor role blocked from raw transcript access.",
        )
        raise

    _enforce_session_access(request, session)
    bind_session_context(request, session.context)
    bundle = get_domain_bundle()
    scenario = bundle.scenarios[session.scenario_id]
    persona = bundle.personas[scenario.doctor_persona_id]

    log_sensitive_access(
        request,
        action="transcript.read",
        target_type="session",
        target_id=session_id,
        learner_id=session.learner_id,
        result="granted",
        detail=f"Transcript read by {get_viewer_role(request) or 'unknown'} role.",
    )

    return GetSessionResponse(
        session_id=session.session_id,
        scenario_id=session.scenario_id,
        learner_id=session.learner_id,
        status=session.status.value,
        turn_count=session.turn_count,
        started_at=session.started_at,
        updated_at=session.updated_at,
        scenario=_scenario_response(scenario, persona),
        coach_continuity=session.continuity_context,
        turns=[
            TurnSnapshotResponse(
                turn_index=turn.turn_index,
                user_message=turn.user_message,
                doctor_reply=turn.doctor_reply,
                director_phase=turn.director_phase,
                director_events=list(turn.director_events),
                created_at=turn.created_at,
                persona_id=turn.persona_id,
            )
            for turn in session.turns
        ],
        experiment_context=summarize_prompt_context(session.prompt_context),
    )


@app.get("/v1/sessions/{session_id}/summary", response_model=SessionSummaryResponse)
def get_session_summary(request: Request, session_id: str) -> SessionSummaryResponse:
    """Redacted session summary accessible to supervisors (no transcript data)."""
    org_id = get_org_id(request)
    bind_request_metadata(request, action_id="get_session_summary", session_id=session_id)
    bundle = get_domain_bundle()
    session_engine: SessionEngine = app.state.session_engine
    try:
        session = session_engine.get_session(session_id, org_id=org_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Enforce learner access but NOT the supervisor transcript block
    # (this endpoint intentionally provides a redacted view)
    _enforce_learner_access(request, session.learner_id)
    bind_session_context(request, session.context)

    review = session.review if isinstance(session.review, dict) else {}
    overall_score = review.get("overall_score")
    overall_band = review.get("overall_band")
    priority_subskills = (
        list(review.get("priority_subskills", []))
        if isinstance(review.get("priority_subskills"), list)
        else []
    )
    compliance_flags = review.get("compliance_flags", [])
    max_severity = None
    severity_order = ["critical", "high", "medium", "low"]
    if isinstance(compliance_flags, list):
        severities_found = sorted(
            set(
                str(f.get("severity", "")).lower()
                for f in compliance_flags
                if isinstance(f, dict)
            ),
            key=lambda s: severity_order.index(s) if s in severity_order else 99,
        )
        max_severity = severities_found[0] if severities_found else None

    log_sensitive_access(
        request,
        action="session.summary.read",
        target_type="session",
        target_id=session_id,
        learner_id=session.learner_id,
        result="granted",
        detail=f"Session summary read by {get_viewer_role(request) or 'unknown'} role.",
    )

    return SessionSummaryResponse(
        session_id=session.session_id,
        scenario_id=session.scenario_id,
        learner_hash=hashlib.sha256(
            session.learner_id.encode("utf-8")
        ).hexdigest()[:12] if session.learner_id else None,
        status=session.status.value,
        finish_reason=session.finish_reason,
        turn_count=session.turn_count,
        overall_score=overall_score if isinstance(overall_score, int) else None,
        overall_band=str(overall_band) if overall_band else None,
        priority_subskills=priority_subskills,
        max_compliance_severity=max_severity,
        started_at=session.started_at,
        updated_at=session.updated_at,
        review_ready=bool(review),
    )


@app.post("/v1/sessions/{session_id}/turn", response_model=SendTurnResponse)
def send_turn(request: Request, session_id: str, payload: SendTurnRequest) -> SendTurnResponse:
    org_id = get_org_id(request)
    bind_request_metadata(request, action_id="send_turn", session_id=session_id)
    bundle = get_domain_bundle()
    session_engine: SessionEngine = app.state.session_engine
    try:
        session = session_engine.get_session(session_id, org_id=org_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    _enforce_session_access(request, session)
    bind_session_context(request, session.context)
    scenario = bundle.scenarios[session.scenario_id]
    persona_id = payload.persona_id or scenario.doctor_persona_id
    if persona_id not in bundle.personas:
        raise HTTPException(status_code=404, detail=f"Unknown persona_id: {persona_id}")
    persona = bundle.personas[persona_id]
    
    try:
        result = session_engine.send_turn(
            session_id=session_id,
            user_message=payload.message,
            scenario=scenario,
            persona=persona,
        )
    except SessionTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    bind_session_context(request, session.context)
    return SendTurnResponse(
        session_id=result.session_id,
        status=result.status.value if isinstance(result.status, SessionStatus) else str(result.status),
        turn_index=result.turn_index,
        doctor_reply=result.doctor_reply,
        persona_id=persona_id,
        director=DirectorPayload(
            phase=result.director.phase,
            events=result.director.events,
            should_finish=result.director.should_finish,
            recommended_action=result.director.recommended_action,
        ),
    )


@app.post("/v1/sessions/{session_id}/turn/voice", response_model=SendTurnResponse)
async def send_voice_turn(
    request: Request, 
    session_id: str, 
    audio: UploadFile = File(...)
) -> SendTurnResponse:
    org_id = get_org_id(request)
    bind_request_metadata(request, action_id="send_voice_turn", session_id=session_id)
    bundle = get_domain_bundle()
    session_engine: SessionEngine = app.state.session_engine
    voice_provider = app.state.voice_provider
    
    try:
        session = session_engine.get_session(session_id, org_id=org_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    _enforce_session_access(request, session)
    bind_session_context(request, session.context)
    
    # Transcribe
    audio_content = await audio.read()
    transcription = voice_provider.transcribe(audio_content, filename=audio.filename or "audio.wav")
    
    scenario = bundle.scenarios[session.scenario_id]
    persona = bundle.personas[scenario.doctor_persona_id]
    
    try:
        result = session_engine.send_turn(
            session_id=session_id,
            user_message=transcription,
            scenario=scenario,
            persona=persona,
        )
    except SessionTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return SendTurnResponse(
        session_id=result.session_id,
        status=result.status.value if isinstance(result.status, SessionStatus) else str(result.status),
        turn_index=result.turn_index,
        doctor_reply=result.doctor_reply,
        persona_id=scenario.doctor_persona_id,
        director=DirectorPayload(
            phase=result.director.phase,
            events=result.director.events,
            should_finish=result.director.should_finish,
            recommended_action=result.director.recommended_action,
        ),
    )


@app.post("/v1/sessions/{session_id}/finish", response_model=FinishSessionResponse)
def finish_session(request: Request, session_id: str) -> FinishSessionResponse:
    org_id = get_org_id(request)
    bind_request_metadata(request, action_id="finish_session", session_id=session_id)
    bundle = get_domain_bundle()
    session_engine: SessionEngine = app.state.session_engine
    progress_tracker: ProgressTracker = app.state.progress_tracker
    model_artifact_generator = app.state.model_artifact_generator
    try:
        session = session_engine.get_session(session_id, org_id=org_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    _enforce_session_access(request, session)
    bind_session_context(request, session.context)
    was_already_finalized = session.status == SessionStatus.FINALIZED
    scenario = bundle.scenarios[session.scenario_id]
    subskill_weights = {
        skill_id: float(skill_payload["weight"])
        for skill_id, skill_payload in bundle.skill_model["subskills"].items()
    }
    try:
        finalized = session_engine.finish_session(
            session_id=session_id,
            scenario_focus_subskills=scenario.focus_subskills,
            subskill_weights=subskill_weights,
            skill_model=bundle.skill_model,
            diagnosis_types=bundle.diagnosis_types,
            compliance_rules=bundle.compliance_rules,
            score_schema=bundle.score_schema,
            judge_review_schema=bundle.judge_review_schema,
            coach_feedback_schema=bundle.coach_feedback_schema,
            compliance_flags_schema=bundle.compliance_flags_schema,
            model_artifact_generator=model_artifact_generator,
        )
    except SessionTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SessionEvaluationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    bind_session_context(request, finalized.context)

    # Evaluate training plan achievement if an admin plan was active
    review = finalized.review or {}
    training_plan_service: TrainingPlanService | None = app.state.training_plan_service
    continuity_context = finalized.continuity_context or {}
    training_plan_data = continuity_context.get("training_plan") if isinstance(continuity_context, dict) else None
    if training_plan_service is not None and isinstance(training_plan_data, dict):
        plan_id = training_plan_data.get("plan_id")
        if isinstance(plan_id, str) and plan_id:
            try:
                plan = training_plan_service.get_plan(plan_id)
                plan_achievement = training_plan_service.evaluate_plan_achievement(
                    plan, review=review
                )
                # Inject into continuity channel for downstream processing
                continuity_channel = review.get("continuity_channel", {})
                if not isinstance(continuity_channel, dict):
                    continuity_channel = {}
                continuity_channel["training_plan_achievement"] = plan_achievement
                continuity_channel["training_plan_id"] = plan_id
                review["continuity_channel"] = continuity_channel
                try:
                    training_plan_service.maybe_complete_plan(plan_id, plan_achievement)
                except Exception:
                    pass  # Non-critical: session finalize never breaks on plan completion
            except TrainingPlanNotFoundError:
                pass

    if was_already_finalized:
        try:
            progress_snapshot = progress_tracker.get_snapshot(finalized.learner_id, org_id=org_id)
        except LearnerProgressNotFoundError:
            progress_snapshot = progress_tracker.apply_session_result(
                scenario_title=scenario.title,
                scenario_difficulty=scenario.difficulty,
                focus_subskills=scenario.focus_subskills,
                persona_id=scenario.doctor_persona_id,
                persona_label=str(bundle.personas[scenario.doctor_persona_id].get("label", "")),
                finish_reason=finalized.finish_reason,
                review=review,
                session_context=finalized.context,
            )
    else:
        progress_snapshot = progress_tracker.apply_session_result(
            scenario_title=scenario.title,
            scenario_difficulty=scenario.difficulty,
            focus_subskills=scenario.focus_subskills,
            persona_id=scenario.doctor_persona_id,
            persona_label=str(bundle.personas[scenario.doctor_persona_id].get("label", "")),
            finish_reason=finalized.finish_reason,
            review=finalized.review or {},
            session_context=finalized.context,
        )

    return FinishSessionResponse(
        session_id=finalized.session_id,
        scenario_id=finalized.scenario_id,
        learner_id=finalized.learner_id,
        status=finalized.status.value,
        finish_reason=finalized.finish_reason or "unknown",
        review=review,
        coach_continuity=finalized.continuity_context,
        progress_snapshot=progress_snapshot,
        experiment_context=summarize_prompt_context(finalized.prompt_context),
    )


@app.get("/v1/sessions/{session_id}/review", response_model=GetReviewResponse)
def get_review(request: Request, session_id: str) -> GetReviewResponse:
    org_id = get_org_id(request)
    bind_request_metadata(request, action_id="get_review", session_id=session_id)
    bundle = get_domain_bundle()
    session_engine: SessionEngine = app.state.session_engine
    progress_tracker: ProgressTracker = app.state.progress_tracker
    try:
        session = session_engine.get_review(session_id, org_id=org_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionReviewUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        _enforce_session_access(request, session)
    except HTTPException:
        log_sensitive_access(
            request,
            action="review.read",
            target_type="session",
            target_id=session_id,
            learner_id=session.learner_id,
            result="denied",
            detail=f"Role {get_viewer_role(request) or 'unknown'} denied review access.",
        )
        raise

    bind_session_context(request, session.context)
    scenario = bundle.scenarios[session.scenario_id]
    persona = bundle.personas[scenario.doctor_persona_id]
    try:
        progress_snapshot = progress_tracker.get_snapshot(session.learner_id, org_id=org_id)
        coach_memory = (
            progress_snapshot.get("coach_memory", {})
            if isinstance(progress_snapshot, dict)
            else {}
        )
    except LearnerProgressNotFoundError:
        coach_memory = None

    log_sensitive_access(
        request,
        action="review.read",
        target_type="session",
        target_id=session_id,
        learner_id=session.learner_id,
        result="granted",
        detail=f"Review read by {get_viewer_role(request) or 'unknown'} role.",
    )

    return GetReviewResponse(
        session_id=session.session_id,
        scenario_id=session.scenario_id,
        learner_id=session.learner_id,
        status=session.status.value,
        finish_reason=session.finish_reason or "unknown",
        turn_count=session.turn_count,
        started_at=session.started_at,
        updated_at=session.updated_at,
        scenario=_scenario_response(scenario, persona),
        review=session.review or {},
        coach_continuity=session.continuity_context,
        coach_memory=coach_memory,
        experiment_context=summarize_prompt_context(session.prompt_context),
    )


@app.get("/v1/learners/{learner_id}/progress", response_model=GetProgressSnapshotResponse)
def get_progress_snapshot(request: Request, learner_id: str) -> GetProgressSnapshotResponse:
    org_id = get_org_id(request)
    bind_request_metadata(
        request,
        action_id="get_progress_snapshot",
        learner_id=learner_id,
    )
    try:
        _enforce_learner_access(request, learner_id)
    except HTTPException:
        log_sensitive_access(
            request,
            action="progress.read",
            target_type="learner_progress",
            target_id=learner_id,
            learner_id=learner_id,
            result="denied",
            detail=f"Role {get_viewer_role(request) or 'unknown'} denied progress access for learner.",
        )
        raise
    progress_tracker: ProgressTracker = app.state.progress_tracker
    try:
        snapshot = progress_tracker.get_snapshot(learner_id, org_id=org_id)
    except LearnerProgressNotFoundError as exc:
        log_sensitive_access(
            request,
            action="progress.read",
            target_type="learner_progress",
            target_id=learner_id,
            learner_id=learner_id,
            result="denied",
            detail="Learner progress not found.",
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    log_sensitive_access(
        request,
        action="progress.read",
        target_type="learner_progress",
        target_id=learner_id,
        learner_id=learner_id,
        result="granted",
        detail=f"Progress read by {get_viewer_role(request) or 'unknown'} role.",
    )
    return GetProgressSnapshotResponse(**snapshot)


@app.get(
    "/v1/organizations/{organization_id}/reports",
    response_model=GetOrganizationReportsResponse,
)
def get_organization_reports(
    request: Request,
    organization_id: str,
) -> GetOrganizationReportsResponse:
    bind_request_metadata(request, action_id="get_organization_reports")
    try:
        _enforce_organization_report_access(request)
    except HTTPException:
        log_sensitive_access(
            request,
            action="report.read",
            target_type="organization_report",
            target_id=organization_id,
            result="denied",
            detail=f"Role {get_viewer_role(request) or 'unknown'} blocked from organization reports.",
        )
        raise
    service: OrganizationReportService = app.state.organization_report_service
    try:
        payload = service.build_report(
            organization_id,
            request_org_id=get_org_id(request),
        )
    except OrganizationReportAccessError as exc:
        log_sensitive_access(
            request,
            action="report.read",
            target_type="organization_report",
            target_id=organization_id,
            result="denied",
            detail=f"Organization report access error: {exc}",
        )
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_sensitive_access(
        request,
        action="report.read",
        target_type="organization_report",
        target_id=organization_id,
        result="granted",
        detail=f"Organization report read by {get_viewer_role(request) or 'unknown'} role.",
    )
    return GetOrganizationReportsResponse(**payload)


@app.get("/v1/sessions/{session_id}/events", response_model=GetSessionEventsResponse)
def get_session_events(request: Request, session_id: str) -> GetSessionEventsResponse:
    org_id = get_org_id(request)
    bind_request_metadata(request, action_id="get_session_events", session_id=session_id)
    session_engine: SessionEngine = app.state.session_engine
    event_store: EventStore = app.state.event_store
    try:
        session = session_engine.get_session(session_id, org_id=org_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        _enforce_supervisor_transcript_policy(request, learner_id=session.learner_id)
    except HTTPException:
        log_sensitive_access(
            request,
            action="transcript.events.read",
            target_type="session",
            target_id=session_id,
            learner_id=session.learner_id,
            result="denied",
            detail="Supervisor role blocked from session events.",
        )
        raise

    try:
        _enforce_session_access(request, session)
    except HTTPException:
        log_sensitive_access(
            request,
            action="transcript.events.read",
            target_type="session",
            target_id=session_id,
            learner_id=session.learner_id,
            result="denied",
            detail=f"Role {get_viewer_role(request) or 'unknown'} denied session events access.",
        )
        raise

    bind_session_context(request, session.context)
    events = event_store.list_events(session_id, org_id=org_id)

    log_sensitive_access(
        request,
        action="transcript.events.read",
        target_type="session",
        target_id=session_id,
        learner_id=session.learner_id,
        result="granted",
        detail=f"Session events ({len(events)} events) read by {get_viewer_role(request) or 'unknown'} role.",
    )
    return GetSessionEventsResponse(
        session_id=session_id,
        event_count=len(events),
        events=events,
    )


@app.get("/v1/evaluation-gates", response_model=GetEvaluationGatesResponse)
def get_evaluation_gates(request: Request) -> GetEvaluationGatesResponse:
    bind_request_metadata(request, action_id="get_evaluation_gates")
    try:
        _enforce_admin_operation_access(request)
    except HTTPException:
        log_sensitive_access(
            request,
            action="admin.evaluation_gates.read",
            target_type="evaluation_gate",
            result="denied",
            detail=f"Role {get_viewer_role(request) or 'unknown'} blocked from evaluation gates.",
        )
        raise
    gate_service: EvaluationGateService = app.state.evaluation_gate_service
    bind_request_metadata(
        request,
        prompt_profile=gate_service.effective_prompt_context["profile_id"],
        experiment_id=gate_service.effective_prompt_context.get("experiment_id"),
    )

    log_sensitive_access(
        request,
        action="admin.evaluation_gates.read",
        target_type="evaluation_gate",
        result="granted",
        detail=f"Evaluation gates read by {get_viewer_role(request) or 'unknown'} role.",
    )
    return GetEvaluationGatesResponse(**gate_service.build_report())


# ── Training Plan CRUD ─────────────────────────────────────────


@app.get("/v1/training-plans", response_model=TrainingPlanListResponse)
def list_training_plans(
    request: Request,
    org_id_query: str | None = None,
    learner_id: str | None = None,
) -> TrainingPlanListResponse:
    bind_request_metadata(request, action_id="list_training_plans")
    try:
        _enforce_admin_operation_access(request)
    except HTTPException:
        log_sensitive_access(
            request,
            action="admin.training_plan.list",
            target_type="training_plan",
            result="denied",
            detail=f"Role {get_viewer_role(request) or 'unknown'} blocked from listing training plans.",
        )
        raise
    service: TrainingPlanService | None = app.state.training_plan_service
    if service is None:
        raise HTTPException(status_code=501, detail="Training plan service not available")
    org_id = org_id_query or get_org_id(request)
    plans = service.list_plans(org_id=org_id, learner_id=learner_id)

    log_sensitive_access(
        request,
        action="admin.training_plan.list",
        target_type="training_plan",
        result="granted",
        detail=f"Listed {len(plans)} training plans by {get_viewer_role(request) or 'unknown'} role.",
    )
    return TrainingPlanListResponse(
        plan_count=len(plans),
        plans=[TrainingPlanResponse(**p.to_dict()) for p in plans],
    )


@app.get("/v1/training-plans/{plan_id}", response_model=TrainingPlanResponse)
def get_training_plan(request: Request, plan_id: str) -> TrainingPlanResponse:
    bind_request_metadata(request, action_id="get_training_plan")
    try:
        _enforce_admin_operation_access(request)
    except HTTPException:
        log_sensitive_access(
            request,
            action="admin.training_plan.read",
            target_type="training_plan",
            target_id=plan_id,
            result="denied",
            detail=f"Role {get_viewer_role(request) or 'unknown'} blocked from reading training plan.",
        )
        raise
    service: TrainingPlanService | None = app.state.training_plan_service
    if service is None:
        raise HTTPException(status_code=501, detail="Training plan service not available")
    try:
        plan = service.get_plan(plan_id)
    except TrainingPlanNotFoundError as exc:
        log_sensitive_access(
            request,
            action="admin.training_plan.read",
            target_type="training_plan",
            target_id=plan_id,
            result="denied",
            detail="Training plan not found.",
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    log_sensitive_access(
        request,
        action="admin.training_plan.read",
        target_type="training_plan",
        target_id=plan_id,
        result="granted",
        detail=f"Training plan read by {get_viewer_role(request) or 'unknown'} role.",
    )
    return TrainingPlanResponse(**plan.to_dict())


# ─── Sharing grant endpoints ───────────────────────────────────────────────

@app.post("/v1/grants", response_model=SharingGrantResponse, status_code=201)
def create_sharing_grant(
    request: Request,
    payload: SharingGrantRequest,
) -> SharingGrantResponse:
    """Create an explicit sharing grant (learner to supervisor)."""
    bind_request_metadata(request, action_id="create_sharing_grant")
    if not _runtime_auth_enabled():
        auth_user = "demo_user"
        org_id = "local"
    else:
        auth_user = get_auth_user(request) or "anonymous"
        org_id = get_org_id(request) or "local"
        if not auth_user or auth_user == "anonymous":
            raise HTTPException(status_code=401, detail="Authentication required to create grants.")

    from services.access_policy import SharingGrant

    grant = SharingGrant(
        grant_id=f"grant_{uuid4().hex[:12]}",
        granter_id=auth_user,
        granter_org_id=org_id,
        grantee_role=payload.grantee_role,
        grantee_scope=payload.grantee_scope,
        artifact_types=payload.artifact_types or list(ALL_ARTIFACT_TYPES),
        reason=payload.reason,
        expires_at=payload.expires_at,
        created_at=_utc_now_iso(),
    )

    app.state.sharing_grants[grant.grant_id] = grant.__dict__

    log_sensitive_access(
        request,
        action="grant.create",
        target_type="sharing_grant",
        target_id=grant.grant_id,
        result="granted",
        detail=f"Grant created: {auth_user} -> {payload.grantee_scope} ({payload.grantee_role})",
    )

    return SharingGrantResponse(**grant.__dict__)


@app.get("/v1/grants", response_model=SharingGrantListResponse)
def list_sharing_grants(request: Request) -> SharingGrantListResponse:
    """List sharing grants for the authenticated user."""
    bind_request_metadata(request, action_id="list_sharing_grants")
    auth_user = get_auth_user(request) or "demo_user"
    org_id = get_org_id(request) or "local"

    grants = [
        SharingGrantResponse(**g)
        for g in app.state.sharing_grants.values()
        if g.get("granter_id") == auth_user or g.get("granter_org_id") == org_id
    ]
    return SharingGrantListResponse(grants=grants)


@app.get("/v1/grants/active", response_model=SharingGrantListResponse)
def get_active_grants(request: Request) -> SharingGrantListResponse:
    """Get active (non-expired) grants visible to this request's role/scope."""
    bind_request_metadata(request, action_id="get_active_grants")
    viewer_role = get_viewer_role(request)
    scope = f"org:{get_org_id(request) or 'local'}"

    active: list[SharingGrantResponse] = []
    for grant_data in app.state.sharing_grants.values():
        expires = grant_data.get("expires_at")
        if expires:
            try:
                if datetime.fromisoformat(expires) < datetime.now(tz=timezone.utc):
                    continue
            except (ValueError, TypeError):
                pass
        if grant_data.get("grantee_role") == viewer_role:
            gs = grant_data.get("grantee_scope", "")
            if gs == scope or gs == f"user:{viewer_role}":
                active.append(SharingGrantResponse(**grant_data))

    return SharingGrantListResponse(grants=active)


@app.delete("/v1/grants/{grant_id}", status_code=204)
def revoke_sharing_grant(request: Request, grant_id: str) -> None:
    """Revoke a sharing grant by ID."""
    bind_request_metadata(request, action_id="revoke_sharing_grant")
    auth_user = get_auth_user(request) or "demo_user"

    if grant_id not in app.state.sharing_grants:
        raise HTTPException(status_code=404, detail="Grant not found.")

    grant = app.state.sharing_grants[grant_id]
    if grant.get("granter_id") != auth_user and get_viewer_role(request) not in ("platform_admin", "organization_admin"):
        raise HTTPException(status_code=403, detail="Only the granter or an admin can revoke a grant.")

    del app.state.sharing_grants[grant_id]

    log_sensitive_access(
        request,
        action="grant.revoke",
        target_type="sharing_grant",
        target_id=grant_id,
        result="granted",
        detail=f"Grant {grant_id} revoked by {auth_user}.",
    )


@app.post("/v1/training-plans", response_model=TrainingPlanResponse, status_code=201)
def create_training_plan(request: Request, payload: TrainingPlanRequest) -> TrainingPlanResponse:
    bind_request_metadata(request, action_id="create_training_plan")
    try:
        _enforce_admin_operation_access(request)
    except HTTPException:
        log_sensitive_access(
            request,
            action="admin.training_plan.create",
            target_type="training_plan",
            result="denied",
            detail=f"Role {get_viewer_role(request) or 'unknown'} blocked from creating training plan.",
        )
        raise
    service: TrainingPlanService | None = app.state.training_plan_service
    if service is None:
        raise HTTPException(status_code=501, detail="Training plan service not available")
    try:
        plan = service.create_plan(payload.model_dump())
    except (ValueError, RuntimeError) as exc:
        log_sensitive_access(
            request,
            action="admin.training_plan.create",
            target_type="training_plan",
            result="denied",
            detail=f"Training plan creation failed: {exc}",
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_sensitive_access(
        request,
        action="admin.training_plan.create",
        target_type="training_plan",
        target_id=plan.plan_id,
        result="granted",
        detail=f"Training plan '{plan.title}' created by {get_viewer_role(request) or 'unknown'} role.",
    )
    return TrainingPlanResponse(**plan.to_dict())


@app.put("/v1/training-plans/{plan_id}", response_model=TrainingPlanResponse)
def update_training_plan(request: Request, plan_id: str, payload: TrainingPlanRequest) -> TrainingPlanResponse:
    bind_request_metadata(request, action_id="update_training_plan")
    try:
        _enforce_admin_operation_access(request)
    except HTTPException:
        log_sensitive_access(
            request,
            action="admin.training_plan.update",
            target_type="training_plan",
            target_id=plan_id,
            result="denied",
            detail=f"Role {get_viewer_role(request) or 'unknown'} blocked from updating training plan.",
        )
        raise
    service: TrainingPlanService | None = app.state.training_plan_service
    if service is None:
        raise HTTPException(status_code=501, detail="Training plan service not available")
    try:
        plan = service.update_plan(plan_id, payload.model_dump())
    except TrainingPlanNotFoundError as exc:
        log_sensitive_access(
            request,
            action="admin.training_plan.update",
            target_type="training_plan",
            target_id=plan_id,
            result="denied",
            detail="Training plan not found for update.",
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        log_sensitive_access(
            request,
            action="admin.training_plan.update",
            target_type="training_plan",
            target_id=plan_id,
            result="denied",
            detail=f"Training plan update failed: {exc}",
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_sensitive_access(
        request,
        action="admin.training_plan.update",
        target_type="training_plan",
        target_id=plan_id,
        result="granted",
        detail=f"Training plan updated by {get_viewer_role(request) or 'unknown'} role.",
    )
    return TrainingPlanResponse(**plan.to_dict())


@app.delete("/v1/training-plans/{plan_id}", status_code=204)
def delete_training_plan(request: Request, plan_id: str) -> None:
    bind_request_metadata(request, action_id="delete_training_plan")
    try:
        _enforce_admin_operation_access(request)
    except HTTPException:
        log_sensitive_access(
            request,
            action="admin.training_plan.delete",
            target_type="training_plan",
            target_id=plan_id,
            result="denied",
            detail=f"Role {get_viewer_role(request) or 'unknown'} blocked from deleting training plan.",
        )
        raise
    service: TrainingPlanService | None = app.state.training_plan_service
    if service is None:
        raise HTTPException(status_code=501, detail="Training plan service not available")
    try:
        service.delete_plan(plan_id)
    except TrainingPlanNotFoundError as exc:
        log_sensitive_access(
            request,
            action="admin.training_plan.delete",
            target_type="training_plan",
            target_id=plan_id,
            result="denied",
            detail="Training plan not found for deletion.",
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    log_sensitive_access(
        request,
        action="admin.training_plan.delete",
        target_type="training_plan",
        target_id=plan_id,
        result="granted",
        detail=f"Training plan deleted by {get_viewer_role(request) or 'unknown'} role.",
    )


@app.post("/v1/training-plans/{plan_id}/assign", response_model=TrainingPlanResponse)
def assign_learners_to_plan(
    request: Request,
    plan_id: str,
    payload: AssignLearnersRequest,
) -> TrainingPlanResponse:
    bind_request_metadata(request, action_id="assign_learners")
    try:
        _enforce_admin_operation_access(request)
    except HTTPException:
        log_sensitive_access(
            request,
            action="admin.training_plan.assign",
            target_type="training_plan",
            target_id=plan_id,
            result="denied",
            detail=f"Role {get_viewer_role(request) or 'unknown'} blocked from assigning learners.",
        )
        raise
    service: TrainingPlanService | None = app.state.training_plan_service
    if service is None:
        raise HTTPException(status_code=501, detail="Training plan service not available")
    try:
        plan = service.assign_learners(plan_id, payload.learner_ids)
    except TrainingPlanNotFoundError as exc:
        log_sensitive_access(
            request,
            action="admin.training_plan.assign",
            target_type="training_plan",
            target_id=plan_id,
            result="denied",
            detail="Training plan not found for assignment.",
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    log_sensitive_access(
        request,
        action="admin.training_plan.assign",
        target_type="training_plan",
        target_id=plan_id,
        result="granted",
        detail=f"Learners {payload.learner_ids} assigned to training plan by {get_viewer_role(request) or 'unknown'} role.",
    )
    return TrainingPlanResponse(**plan.to_dict())


@app.post("/v1/training-plans/{plan_id}/unassign", response_model=TrainingPlanResponse)
def unassign_learners_from_plan(
    request: Request,
    plan_id: str,
    payload: UnassignLearnersRequest,
) -> TrainingPlanResponse:
    bind_request_metadata(request, action_id="unassign_learners")
    try:
        _enforce_admin_operation_access(request)
    except HTTPException:
        log_sensitive_access(
            request,
            action="admin.training_plan.unassign",
            target_type="training_plan",
            target_id=plan_id,
            result="denied",
            detail=f"Role {get_viewer_role(request) or 'unknown'} blocked from unassigning learners.",
        )
        raise
    service: TrainingPlanService | None = app.state.training_plan_service
    if service is None:
        raise HTTPException(status_code=501, detail="Training plan service not available")
    try:
        plan = service.unassign_learners(plan_id, payload.learner_ids)
    except TrainingPlanNotFoundError as exc:
        log_sensitive_access(
            request,
            action="admin.training_plan.unassign",
            target_type="training_plan",
            target_id=plan_id,
            result="denied",
            detail="Training plan not found for unassignment.",
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    log_sensitive_access(
        request,
        action="admin.training_plan.unassign",
        target_type="training_plan",
        target_id=plan_id,
        result="granted",
        detail=f"Learners {payload.learner_ids} unassigned from training plan by {get_viewer_role(request) or 'unknown'} role.",
    )
    return TrainingPlanResponse(**plan.to_dict())


# ── Plan Progress ──────────────────────────────────────────────


class PlanProgressLearnerRow(BaseModel):
    learner_id: str
    total_sessions: int
    finalized_sessions: int
    subskill_scores: dict[str, float]
    achievement_status: str  # "achieved" | "partially_achieved" | "not_achieved"
    achievement_rate: float


class PlanProgressResponse(BaseModel):
    plan_id: str
    title: str
    status: str
    target_subskills: list[str]
    success_threshold: float
    assigned_learners: list[str]
    learners: list[PlanProgressLearnerRow]
    overall_achievement_rate: float


@app.get("/v1/training-plans/{plan_id}/progress", response_model=PlanProgressResponse)
def get_training_plan_progress(request: Request, plan_id: str) -> PlanProgressResponse:
    bind_request_metadata(request, action_id="get_training_plan_progress")
    try:
        _enforce_organization_report_access(request)
    except HTTPException:
        log_sensitive_access(
            request,
            action="training_plan.progress.read",
            target_type="training_plan",
            target_id=plan_id,
            result="denied",
            detail=f"Role {get_viewer_role(request) or 'unknown'} blocked from reading plan progress.",
        )
        raise
    service: TrainingPlanService | None = app.state.training_plan_service
    if service is None:
        raise HTTPException(status_code=501, detail="Training plan service not available")
    try:
        plan = service.get_plan(plan_id)
    except TrainingPlanNotFoundError as exc:
        log_sensitive_access(
            request,
            action="training_plan.progress.read",
            target_type="training_plan",
            target_id=plan_id,
            result="denied",
            detail="Training plan not found.",
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    org_id = get_org_id(request)
    session_store = app.state.session_store
    all_sessions = session_store.list_all(org_id=org_id)
    target_subskills = plan.target_subskills
    threshold = plan.success_threshold

    learner_rows: list[PlanProgressLearnerRow] = []
    assigned_set = set(plan.assigned_learners)

    for learner_id in sorted(assigned_set):
        learner_sessions = [
            s for s in all_sessions
            if str(s.get("learner_id", "")).strip() == learner_id
        ]
        total = len(learner_sessions)
        finalized = [s for s in learner_sessions if s.get("status") == "finalized"]
        finalized_count = len(finalized)

        subskill_scores: dict[str, float] = {}
        for subskill_id in target_subskills:
            best_score = 0.0
            for session in finalized:
                review = session.get("review") or {}
                if not isinstance(review, dict):
                    continue
                subskills = review.get("subskills") or {}
                if not isinstance(subskills, dict):
                    continue
                entry = subskills.get(subskill_id) or {}
                if isinstance(entry, dict):
                    score = float(entry.get("score", 0.0))
                    if score > best_score:
                        best_score = score
            subskill_scores[subskill_id] = best_score

        if target_subskills:
            achieved_count = sum(
                1 for sid in target_subskills
                if subskill_scores.get(sid, 0.0) >= threshold
            )
            achievement_rate = achieved_count / len(target_subskills)
        else:
            achievement_rate = 0.0

        if achievement_rate >= 1.0:
            achievement_status = "achieved"
        elif achievement_rate > 0:
            achievement_status = "partially_achieved"
        else:
            achievement_status = "not_achieved"

        learner_rows.append(PlanProgressLearnerRow(
            learner_id=learner_id,
            total_sessions=total,
            finalized_sessions=finalized_count,
            subskill_scores=subskill_scores,
            achievement_status=achievement_status,
            achievement_rate=round(achievement_rate, 2),
        ))

    if learner_rows:
        overall_rate = round(
            sum(r.achievement_rate for r in learner_rows) / len(learner_rows), 2
        )
    else:
        overall_rate = 0.0

    log_sensitive_access(
        request,
        action="training_plan.progress.read",
        target_type="training_plan",
        target_id=plan_id,
        result="granted",
        detail=f"Plan progress read by {get_viewer_role(request) or 'unknown'} role.",
    )
    return PlanProgressResponse(
        plan_id=plan.plan_id,
        title=plan.title,
        status=plan.status,
        target_subskills=target_subskills,
        success_threshold=threshold,
        assigned_learners=plan.assigned_learners,
        learners=learner_rows,
        overall_achievement_rate=overall_rate,
    )

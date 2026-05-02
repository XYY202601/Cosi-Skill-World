const TRACE_RESPONSE_HEADERS = [
  "x-request-id",
  "x-trace-id",
  "x-session-id",
  "x-turn-id",
  "x-service-name",
] as const;

export type TraceResponseHeader = (typeof TRACE_RESPONSE_HEADERS)[number];
export type Difficulty = "easy" | "medium" | "hard";
export type TeachingPlanEvidence = {
  summary: string;
  subskill_id?: string | null;
  turn_index?: number | null;
  session_id?: string | null;
  scenario_id?: string | null;
  scenario_title?: string | null;
};

export type TeachingPlan = {
  version?: number;
  focus_subskills: string[];
  reason: string;
  target_behavior: string;
  success_criterion: string;
  score_threshold: number;
  prior_evidence?: TeachingPlanEvidence[];
};

export type TeachingPlanSnapshot = {
  snapshot_id: string;
  plan_version: number;
  frozen_at: string;
  source_updated_at?: string | null;
  source_session_id?: string | null;
  source_scenario_id?: string | null;
  source_scenario_title?: string | null;
};

export type TeachingPlanAchievement = {
  status: "achieved" | "partially_achieved" | "not_achieved" | "no_plan";
  achieved_count: number;
  total_count: number;
  threshold: number;
};

export type RuntimeErrorPayload = {
  detail?: unknown;
};

export type PromptContractSummary = {
  version: number;
  [key: string]: unknown;
};

export type PromptContextSummary = {
  profile_id: string;
  experiment_id?: string | null;
  flags: string[];
  contracts: Record<string, PromptContractSummary>;
};

export type ScenarioSummary = {
  id: string;
  title: string;
  difficulty: Difficulty;
  focus_subskills: string[];
  doctor_persona_id: string;
  persona_label: string;
  persona_attitude: string;
  persona_time_pressure: string;
  persona_specialty: string;
  max_turns: number;
  success_criteria: string[];
  failure_patterns: string[];
};

export type ScenarioListResponse = {
  domain_id: string;
  scenario_count: number;
  scenarios: ScenarioSummary[];
};

export type ScenarioRecommendation = {
  scenario_id: string;
  title: string;
  difficulty: string;
  target_subskills: string[];
  reason: string;
  recommendation_type?: string;
  evidence_source?: string;
  stop_condition?: string;
  expected_difficulty?: string | null;
  suggested_repetition_count?: number;
  reason_category?: string;
  urgency?: string;
  urgency_reason?: string | null;
};

export type PracticePathEntry = ScenarioRecommendation & {
  step_index: number;
};

export type WeaknessCluster = {
  cluster_id: string;
  subskills: string[];
  occurrences: number;
  last_seen_at: string;
};

export type ProgressSubskill = {
  exp: number;
  level: number;
  last_score: number;
  trend: string;
  rolling_average?: number;
  history_count?: number;
  recent_scores?: number[];
  mastery_status?: "needs_practice" | "improving" | "stable" | "mastered" | string;
  review_status?: "focus_now" | "maintain" | "soon" | "due" | string;
  sessions_since_focus?: number | null;
  next_review_in_sessions?: number | null;
  status_reason?: string;
};

export type ProgressHistoryItem = {
  session_id: string;
  scenario_id: string;
  scenario_title?: string;
  difficulty?: string;
  persona_id?: string;
  persona_label?: string;
  skill_id?: string;
  prompt_profile?: string;
  experiment_id?: string | null;
  trace_id?: string;
  finish_reason?: string;
  overall_score: number;
  overall_band?: string;
  exp_gain?: number;
  weak_subskills?: string[];
  priority_subskills?: string[];
  diagnosis_summaries?: string[];
  max_compliance_severity?: string | null;
  compliance_severities?: string[];
  teaching_plan_achievement?: TeachingPlanAchievement | null;
  teaching_plan_snapshot_id?: string | null;
  timestamp: string;
};

export type CoachMemory = {
  version?: number;
  summary?: string;
  active_focus_subskills?: string[];
  next_actions?: string[];
  last_teaching_plan_achievement?: TeachingPlanAchievement;
  recurring_weaknesses?: string[];
  persistent_weaknesses?: string[];
  recent_personas?: string[];
  last_diagnosis_summaries?: string[];
  last_session?: {
    session_id?: string;
    scenario_id?: string;
    scenario_title?: string;
    persona_label?: string;
    overall_score?: number | null;
    timestamp?: string;
  };
  teaching_plan?: TeachingPlan | null;
  updated_at?: string;
  [key: string]: unknown;
};

export type PerformanceAnalytics = {
  overall_trend: "improving" | "stable" | "declining";
  rolling_average: number;
  plateau_risk: boolean;
  session_count: number;
  last_updated: string;
};

export type CurriculumScenarioProgress = {
  scenario_id: string;
  title: string;
  attempt_count: number;
  required: boolean;
  remaining_repetitions: number;
};

export type CurriculumProgressMetrics = {
  completed_sessions: number;
  required_scenarios_completed: number;
  required_scenarios_total: number;
  average_stage_score: number;
  target_subskill_average: number;
};

export type CurriculumProgress = {
  curriculum_id: string;
  curriculum_title: string;
  current_stage_id: string;
  current_stage_title: string;
  current_stage_description: string;
  current_module_id: string;
  current_module_title: string;
  stage_position: number;
  total_stages: number;
  status: "in_progress" | "completed" | string;
  mastery_status: "needs_practice" | "improving" | "stable" | "mastered" | string;
  review_status: "focus_now" | "maintain" | "soon" | "due" | string;
  next_review_in_sessions?: number | null;
  target_subskills: string[];
  recommended_repetition: number;
  current_stage_scenarios: CurriculumScenarioProgress[];
  completed_stage_ids: string[];
  rationale: string;
  next_stage_id?: string | null;
  next_stage_title?: string | null;
  attention_reason: string;
  metrics: CurriculumProgressMetrics;
};

export type SkillWorldNode = {
  node_id: string;
  kind: string;
  stage_id: string;
  title: string;
  description: string;
  module_id: string;
  position: number;
  status: "completed" | "active" | "locked" | string;
  progress_percent: number;
  target_subskills: string[];
  scenario_ids: string[];
  completed_scenario_count: number;
  scenario_count: number;
  required_scenarios_completed: number;
  required_scenarios_total: number;
  mastery_status: string;
  review_status: string;
  rationale: string;
  last_trained_at?: string | null;
};

export type SkillWorldAchievement = {
  achievement_id: string;
  kind: string;
  title: string;
  description: string;
  status: "earned" | string;
  earned_at?: string | null;
  evidence?: Record<string, unknown>;
};

export type SkillWorld = {
  version: number;
  map_id: string;
  title: string;
  active_node_id?: string | null;
  summary: {
    completed_stage_count: number;
    total_stage_count: number;
    map_progress_percent: number;
    earned_achievement_count: number;
    mastered_subskill_count: number;
    total_subskill_count: number;
    current_stage_title: string;
  };
  nodes: SkillWorldNode[];
  achievements: SkillWorldAchievement[];
};

export type ProgressSnapshotResponse = {
  learner_id: string;
  total_sessions: number;
  total_exp: number;
  level: number;
  updated_at: string;
  latest_recommendations: ScenarioRecommendation[];
  practice_path?: PracticePathEntry[];
  weakness_clusters: WeaknessCluster[];
  subskills: Record<string, ProgressSubskill>;
  recent_history: ProgressHistoryItem[];
  coach_memory: CoachMemory;
  curriculum: CurriculumProgress;
  skill_world: SkillWorld;
  performance_analytics?: PerformanceAnalytics;
};

export type CoachContinuity = {
  version?: number;
  summary?: string;
  scenario_title_override?: string;
  carryover_focus_subskills?: string[];
  scenario_focus_subskills?: string[];
  suggested_focus_subskills?: string[];
  next_actions?: string[];
  teaching_plan?: TeachingPlan | null;
  teaching_plan_snapshot?: TeachingPlanSnapshot | null;
  recent_personas?: string[];
  persona?: {
    more_receptive_when?: string[];
    less_receptive_when?: string[];
  };
  [key: string]: unknown;
};

export type DirectorPayload = {
  phase: string;
  events: string[];
  should_finish: boolean;
  recommended_action: string;
};

export type StartSessionResponse = {
  session_id: string;
  scenario_id: string;
  learner_id: string;
  status: string;
  scenario: ScenarioSummary;
  coach_continuity: CoachContinuity;
  experiment_context: PromptContextSummary;
};

export type SendTurnResponse = {
  session_id: string;
  status: "initialized" | "running" | "awaiting_finish" | "finalized";
  turn_index: number;
  doctor_reply: string;
  director: DirectorPayload;
};

export type TurnSnapshot = {
  turn_index: number;
  user_message: string;
  doctor_reply: string;
  director_phase: string;
  director_events: string[];
  created_at: string;
};

export type SessionResponse = {
  session_id: string;
  scenario_id: string;
  learner_id: string;
  status: string;
  turn_count: number;
  started_at: string;
  updated_at: string;
  scenario: ScenarioSummary;
  coach_continuity: CoachContinuity;
  turns: TurnSnapshot[];
  experiment_context: PromptContextSummary;
};

export type SessionSummaryResponse = {
  session_id: string;
  scenario_id: string;
  learner_hash?: string | null;
  status: string;
  finish_reason?: string | null;
  turn_count: number;
  overall_score?: number | null;
  overall_band?: string | null;
  priority_subskills: string[];
  max_compliance_severity?: string | null;
  started_at: string;
  updated_at: string;
  review_ready: boolean;
  detail: string;
};

export type ReviewEvidenceObject = {
  summary?: string;
  turn_index?: number;
  speaker?: string;
  excerpt?: string;
  tags?: string[];
};

export type ReviewEvidence = string | ReviewEvidenceObject;

export type ReviewSubskillScore = {
  score: number;
  evidence: ReviewEvidence[];
};

export type VoiceSignalScore = {
  score: number;
  evidence: ReviewEvidence[];
};

export type ReviewDiagnosisItem = {
  id?: string;
  kind?: string;
  severity?: string;
  summary?: string;
  related_subskills?: string[];
  recommendation_focus?: string[];
};

export type RuntimeReview = {
  display_title?: string;
  rubric_version?: number;
  overall_score?: number;
  overall_band?: string;
  strengths?: string[];
  priority_subskills?: string[];
  subskills?: Record<string, ReviewSubskillScore>;
  voice_signals?: Record<string, VoiceSignalScore>;
  diagnosis?: {
    primary?: ReviewDiagnosisItem[];
    selection_basis?: string;
  };
  coaching_feedback?: {
    version?: number;
    focus_subskills?: string[];
    next_actions?: string[];
  };
  compliance_flags?: Array<{
    rule_id?: string;
    tag?: string;
    severity?: string;
    summary?: string;
    related_diagnosis_types?: string[];
    evidence?: ReviewEvidence[];
    required_handling?: string;
    remedial_priority?: number;
  }>;
  compliance_channel?: {
    flags: Array<Record<string, unknown>>;
    overall_status: string;
    remedial_required: boolean;
  };
  continuity_channel?: {
    score: number;
    highlights: string[];
    carryover_subskills: string[];
    teaching_plan_achievement?: TeachingPlanAchievement;
  };
  meta?: {
    finish_reason?: string;
    turn_count?: number;
    evaluation_mode?: string;
    artifact_sources?: Record<string, string>;
    artifact_modes?: Record<string, string>;
    fallback_reasons?: string[];
    model_meta?: Record<string, unknown>;
    prompting?: PromptContextSummary;
    context?: {
      skill_id?: string;
      session_id?: string;
      turn_id?: string | null;
      learner_id?: string;
      scenario_id?: string;
      persona_id?: string;
      prompt_profile?: string;
      experiment_id?: string | null;
      prompt_flags?: string[];
      locale?: string;
      trace_id?: string;
      continuity?: Record<string, unknown>;
    };
  };
  [key: string]: unknown;
};

export type FinishSessionResponse = {
  session_id: string;
  scenario_id: string;
  learner_id: string;
  status: string;
  finish_reason: string;
  review: RuntimeReview;
  coach_continuity: CoachContinuity;
  progress_snapshot: ProgressSnapshotResponse;
  experiment_context: PromptContextSummary;
};

export type ReviewResponse = {
  session_id: string;
  scenario_id: string;
  learner_id: string;
  status: string;
  finish_reason: string;
  turn_count: number;
  started_at: string;
  updated_at: string;
  scenario: ScenarioSummary;
  review: RuntimeReview;
  coach_continuity?: CoachContinuity | null;
  coach_memory?: CoachMemory | null;
  experiment_context: PromptContextSummary;
};

export type SessionEventTurnContent = {
  turn_index?: number;
  director_phase?: string;
  director_events?: string[];
  recommended_action?: string;
  status?: string;
  director?: DirectorPayload;
  signal_summary?: Record<string, unknown>;
  taxonomy?: Record<string, unknown>;
};

export type SessionEventEnvelope = {
  type: string;
  source: string;
  stage: string;
  content: Record<string, unknown> & SessionEventTurnContent;
  metadata: Record<string, unknown>;
  skill_id: string;
  session_id: string;
  turn_id: string | null;
  seq: number;
  timestamp: string;
  schema_version: string;
};

export type SessionEventsResponse = {
  session_id: string;
  event_count: number;
  events: SessionEventEnvelope[];
};

export type EvaluationGateCheck = {
  name: string;
  passed: boolean;
  detail: string;
};

export type OfflineFixtureResult = {
  fixture_name: string;
  passed: boolean;
  overall_score: number;
  overall_band: string;
};

export type OfflineEvaluationGate = {
  profile_id: string;
  status: string;
  fixture_pass_rate: number;
  fixture_results: OfflineFixtureResult[];
  contract_versions: Record<string, number>;
  output_requirement_counts: Record<string, number>;
  checks: EvaluationGateCheck[];
};

export type OnlineEvaluationGate = {
  profile_id: string;
  experiment_id?: string | null;
  status: string;
  sample_size: number;
  metrics: Record<string, unknown>;
  thresholds: Record<string, unknown>;
  checks: EvaluationGateCheck[];
  updated_at: string;
};

export type PromptRolloutDecision = {
  status: string;
  requested: PromptContextSummary;
  effective: PromptContextSummary;
  stable_profile_id: string;
  allow_blocked_rollout: boolean;
  checks: EvaluationGateCheck[];
};

export type EvaluationGatesResponse = {
  domain_id: string;
  default_profile_id: string;
  rollout: PromptRolloutDecision;
  offline_gates: OfflineEvaluationGate[];
  online_gates: OnlineEvaluationGate[];
};

export type RuntimeRequestContext = {
  orgId?: string | null;
  viewerRole?: string | null;
};

export type OrganizationReportWeakness = {
  subskill_id: string;
  occurrences: number;
  affected_learners: number;
};

export type AttentionReason = {
  code: string;
  detail: string;
  subskill_id?: string | null;
  severity?: string | null;
};

export type OrganizationReviewSummary = {
  session_id: string;
  learner_id: string;
  scenario_id: string;
  scenario_title: string;
  persona_label?: string | null;
  status: string;
  started_at: string;
  updated_at: string;
  finish_reason?: string | null;
  overall_score?: number | null;
  overall_band?: string | null;
  prompt_profile?: string | null;
  max_compliance_severity?: string | null;
  priority_subskills: string[];
  review_ready: boolean;
};

export type OrganizationLearnerSummary = {
  learner_id: string;
  learner_hash?: string | null;
  total_sessions: number;
  finalized_sessions: number;
  active_sessions: number;
  average_score?: number | null;
  last_score?: number | null;
  practice_completion_rate: number;
  highest_compliance_severity?: string | null;
  recurring_weaknesses: OrganizationReportWeakness[];
  active_focus_subskills: string[];
  needs_attention: boolean;
  needs_attention_reasons: AttentionReason[];
  latest_session_at?: string | null;
  latest_scenario_title?: string | null;
  recent_reviews: OrganizationReviewSummary[];
};

export type OrganizationTeamSummary = {
  learner_count: number;
  total_sessions: number;
  finalized_sessions: number;
  active_sessions: number;
  average_score?: number | null;
  practice_completion_rate: number;
  compliance_risk_session_count: number;
  high_risk_session_count: number;
  at_risk_learner_count: number;
  recurring_weaknesses: OrganizationReportWeakness[];
  latest_activity_at?: string | null;
};

export type OrganizationReportsResponse = {
  organization_id: string;
  organization_scope: "global" | "organization";
  generated_at: string;
  team_summary: OrganizationTeamSummary;
  learners: OrganizationLearnerSummary[];
};

// ── Training Plan Types ──────────────────────────────────────

export type TrainingPlanItem = {
  plan_id: string;
  org_id: string;
  title: string;
  description: string;
  owner_id: string;
  assigned_learners: string[];
  assigned_cohorts: string[];
  target_subskills: string[];
  required_scenario_ids: string[];
  due_date?: string | null;
  goal_criteria: string;
  success_threshold: number;
  review_cadence: string;
  status: string;
  created_at: string;
  updated_at: string;
  version: number;
};

export type TrainingPlanListResponse = {
  plan_count: number;
  plans: TrainingPlanItem[];
};

export type CreateTrainingPlanRequest = {
  plan_id?: string | null;
  org_id?: string;
  title: string;
  description?: string;
  owner_id?: string;
  assigned_learners?: string[];
  assigned_cohorts?: string[];
  target_subskills?: string[];
  required_scenario_ids?: string[];
  due_date?: string | null;
  goal_criteria?: string;
  success_threshold?: number;
  review_cadence?: string;
  status?: string;
};

export type AssignLearnersRequest = {
  learner_ids: string[];
};

// ── Plan Progress Types ───────────────────────────────────────

export type PlanProgressLearnerRow = {
  learner_id: string;
  total_sessions: number;
  finalized_sessions: number;
  subskill_scores: Record<string, number>;
  achievement_status: "achieved" | "partially_achieved" | "not_achieved";
  achievement_rate: number;
};

export type PlanProgressResponse = {
  plan_id: string;
  title: string;
  status: string;
  target_subskills: string[];
  success_threshold: number;
  assigned_learners: string[];
  learners: PlanProgressLearnerRow[];
  overall_achievement_rate: number;
};

// ── Training Plan API ────────────────────────────────────────

export async function listTrainingPlans(
  context: RuntimeRequestContext = {}
): Promise<TrainingPlanListResponse> {
  return readRuntimeJson<TrainingPlanListResponse>(
    buildRuntimeProxyPath("/api/runtime/training-plans", context),
  );
}

export async function getTrainingPlan(
  planId: string,
  context: RuntimeRequestContext = {},
): Promise<TrainingPlanItem> {
  return readRuntimeJson<TrainingPlanItem>(
    buildRuntimeProxyPath(`/api/runtime/training-plans/${encodeURIComponent(planId)}`, context),
  );
}

export async function createTrainingPlan(
  payload: CreateTrainingPlanRequest,
  context: RuntimeRequestContext = {},
): Promise<TrainingPlanItem> {
  return readRuntimeJson<TrainingPlanItem>(
    buildRuntimeProxyPath("/api/runtime/training-plans", context),
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export async function updateTrainingPlan(
  planId: string,
  payload: CreateTrainingPlanRequest,
  context: RuntimeRequestContext = {},
): Promise<TrainingPlanItem> {
  return readRuntimeJson<TrainingPlanItem>(
    buildRuntimeProxyPath(`/api/runtime/training-plans/${encodeURIComponent(planId)}`, context),
    {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteTrainingPlan(
  planId: string,
  context: RuntimeRequestContext = {},
): Promise<void> {
  const response = await fetch(
    buildRuntimeProxyPath(`/api/runtime/training-plans/${encodeURIComponent(planId)}`, context),
    { method: "DELETE", cache: "no-store" },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(runtimeErrorMessage(payload));
  }
}

export async function assignLearnersToPlan(
  planId: string,
  learnerIds: string[],
  context: RuntimeRequestContext = {},
): Promise<TrainingPlanItem> {
  return readRuntimeJson<TrainingPlanItem>(
    buildRuntimeProxyPath(`/api/runtime/training-plans/${encodeURIComponent(planId)}/assign`, context),
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ learner_ids: learnerIds }),
    },
  );
}

export async function getTrainingPlanProgress(
  planId: string,
  context: RuntimeRequestContext = {},
): Promise<PlanProgressResponse> {
  return readRuntimeJson<PlanProgressResponse>(
    buildRuntimeProxyPath(`/api/runtime/training-plans/${encodeURIComponent(planId)}/progress`, context),
  );
}

export async function unassignLearnersFromPlan(
  planId: string,
  learnerIds: string[],
  context: RuntimeRequestContext = {},
): Promise<TrainingPlanItem> {
  return readRuntimeJson<TrainingPlanItem>(
    buildRuntimeProxyPath(`/api/runtime/training-plans/${encodeURIComponent(planId)}/unassign`, context),
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ learner_ids: learnerIds }),
    },
  );
}


// ── Sharing Grant Types ────────────────────────────────────────────

export type SharingGrantItem = {
  grant_id: string;
  granter_id: string;
  granter_org_id: string;
  grantee_role: string;
  grantee_scope: string;
  artifact_types: string[];
  reason: string;
  expires_at: string | null;
  created_at: string;
};

export type SharingGrantListResponse = {
  grants: SharingGrantItem[];
};

export type CreateSharingGrantRequest = {
  grantee_role?: string;
  grantee_scope: string;
  artifact_types?: string[];
  reason?: string;
  expires_at?: string | null;
};


// ── Sharing Grant API ──────────────────────────────────────────────

export async function listSharingGrants(
  context: RuntimeRequestContext = {},
): Promise<SharingGrantListResponse> {
  return readRuntimeJson<SharingGrantListResponse>(
    buildRuntimeProxyPath("/api/runtime/grants", context),
  );
}

export async function createSharingGrant(
  payload: CreateSharingGrantRequest,
  context: RuntimeRequestContext = {},
): Promise<SharingGrantItem> {
  return readRuntimeJson<SharingGrantItem>(
    buildRuntimeProxyPath("/api/runtime/grants", context),
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export async function getActiveGrants(
  context: RuntimeRequestContext = {},
): Promise<SharingGrantListResponse> {
  return readRuntimeJson<SharingGrantListResponse>(
    buildRuntimeProxyPath("/api/runtime/grants/active", context),
  );
}

export async function revokeSharingGrant(
  grantId: string,
  context: RuntimeRequestContext = {},
): Promise<void> {
  const response = await fetch(
    buildRuntimeProxyPath(`/api/runtime/grants/${encodeURIComponent(grantId)}`, context),
    { method: "DELETE", cache: "no-store" },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(runtimeErrorMessage(payload));
  }
}


// ── Marketplace API ────────────────────────────────────────────────────────

export type MarketplaceInstallationState =
  | "available"
  | "installed"
  | "disabled"
  | "upgrade_available"
  | "blocked";

export type MarketplaceInstallation = {
  skill_id: string;
  org_id: string;
  state: MarketplaceInstallationState;
  installed_version?: string;
  installed_at?: string;
  installed_by?: string;
  updated_at?: string;
  reason?: string;
};

export type MarketplaceSkillItem = {
  id: string;
  name: string;
  version: string;
  registration_enabled: boolean;
  default_for_unscoped_routes: boolean;
  runtime?: {
    app?: string;
    base_path?: string;
    health_path?: string;
    base_url_env?: string;
  };
  marketplace?: {
    title?: string;
    summary?: string;
    provider?: string;
    locales?: string[];
    modality?: string;
    maturity?: string;
    compatibility?: { min_runtime_version?: string };
    privacy?: { data_notes?: string };
  } | null;
  capabilities?: Array<{
    id: string;
    name?: string;
    description?: string;
    actions?: string[];
  }>;
  actions?: Array<{
    id: string;
    capability?: string;
    method?: string;
    path?: string;
    description?: string;
    expose?: string[];
    path_params?: string[];
  }>;
  subskills?: string[];
  installation?: MarketplaceInstallation;
};

export type MarketplaceListResponse = {
  skills: string[];
  default_skill_id: string | null;
  items: MarketplaceSkillItem[];
};

export type OrgSkillsListResponse = {
  org_id: string;
  skills: Record<string, MarketplaceInstallation>;
  count: number;
};

export async function listMarketplaceSkills(
  context: RuntimeRequestContext = {},
): Promise<MarketplaceListResponse> {
  return readRuntimeJson<MarketplaceListResponse>(
    buildRuntimeProxyPath("/api/runtime/marketplace", context),
  );
}

export async function listOrgSkills(
  orgId: string,
  options?: { state?: string },
  context: RuntimeRequestContext = {},
): Promise<OrgSkillsListResponse> {
  const params = new URLSearchParams();
  if (options?.state) params.set("state", options.state);
  const qs = params.toString();
  return readRuntimeJson<OrgSkillsListResponse>(
    buildRuntimeProxyPath(
      `/api/runtime/marketplace/org/${encodeURIComponent(orgId)}/skills${qs ? `?${qs}` : ""}`,
      context,
    ),
  );
}

export async function installOrgSkill(
  orgId: string,
  skillId: string,
  options?: { version?: string; installed_by?: string },
  context: RuntimeRequestContext = {},
): Promise<MarketplaceInstallation> {
  return readRuntimeJson<MarketplaceInstallation>(
    buildRuntimeProxyPath(
      `/api/runtime/marketplace/org/${encodeURIComponent(orgId)}/install`,
      context,
    ),
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        skill_id: skillId,
        ...(options?.version ? { version: options.version } : {}),
        ...(options?.installed_by ? { installed_by: options.installed_by } : {}),
      }),
    },
  );
}

export async function setOrgSkillState(
  orgId: string,
  skillId: string,
  state: string,
  reason?: string,
  context: RuntimeRequestContext = {},
): Promise<MarketplaceInstallation> {
  return readRuntimeJson<MarketplaceInstallation>(
    buildRuntimeProxyPath(
      `/api/runtime/marketplace/org/${encodeURIComponent(orgId)}/skills/${encodeURIComponent(skillId)}/state`,
      context,
    ),
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ state, ...(reason ? { reason } : {}) }),
    },
  );
}

export async function removeOrgSkill(
  orgId: string,
  skillId: string,
  context: RuntimeRequestContext = {},
): Promise<void> {
  const response = await fetch(
    buildRuntimeProxyPath(
      `/api/runtime/marketplace/org/${encodeURIComponent(orgId)}/skills/${encodeURIComponent(skillId)}`,
      context,
    ),
    { method: "DELETE", cache: "no-store" },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(runtimeErrorMessage(payload));
  }
}


// ── Cross-skill Dashboard ────────────────────────────────────────────────

export type CrossSkillDashboardEntry = {
  skill_id: string;
  skill_name: string;
  state: string;
  installed_version: string;
  marketplace?: {
    title?: string;
    summary?: string;
    provider?: string;
    modality?: string;
    maturity?: string;
  } | null;
  progress: {
    has_progress: boolean;
    total_sessions?: number;
    finalized_sessions?: number;
    overall_band?: string | null;
    overall_score?: number | null;
    compliance_risk_count?: number;
  };
};

export type CrossSkillDashboardResponse = {
  org_id: string;
  learner_id: string | null;
  installed_skill_count: number;
  skills: CrossSkillDashboardEntry[];
};

export async function fetchCrossSkillDashboard(
  orgId: string,
  learnerId?: string,
  context: RuntimeRequestContext = {},
): Promise<CrossSkillDashboardResponse> {
  let path = `/api/runtime/marketplace/org/${encodeURIComponent(orgId)}/dashboard`;
  if (learnerId) {
    path += `?learner_id=${encodeURIComponent(learnerId)}`;
  }
  return readRuntimeJson<CrossSkillDashboardResponse>(
    buildRuntimeProxyPath(path, context),
  );
}


export type RuntimeProxyResult = {
  status: number;
  payload: unknown;
  headers: Partial<Record<TraceResponseHeader, string>>;
  upstreamBase: string;
};

const DEFAULT_PLATFORM_API_BASE = "http://127.0.0.1:8000";
const DEFAULT_DIRECT_RUNTIME_API_BASE = "http://127.0.0.1:8100";
const UNSCOPED_ORG_IDS = new Set(["all", "default", "global", "local", "unscoped"]);

// ── Auth mode ─────────────────────────────────────────────────

export function getAuthMode(): "disabled" | "mock" | "oidc" {
  const raw = (process.env.AUTH_MODE || "disabled").trim().toLowerCase();
  if (raw === "mock") return "mock";
  if (raw === "oidc") return "oidc";
  return "disabled";
}

// ── Deploy environment ─────────────────────────────────────────

type DeployEnv = "development" | "staging" | "production";

export function getDeployEnv(): DeployEnv {
  const raw = process.env.DEPLOY_ENV || "development";
  if (raw !== "development" && raw !== "staging" && raw !== "production") {
    return "development";
  }
  return raw;
}

export function validateDeployEnv(): void {
  const deployEnv = getDeployEnv();
  if (deployEnv !== "staging" && deployEnv !== "production") {
    return;
  }
  const resolvedVar = process.env.HERMES_API_BASE || process.env.NEXT_PUBLIC_HERMES_API_BASE;
  if (!resolvedVar) {
    throw new Error(
      `[runtime-api] DEPLOY_ENV=${deployEnv} requires HERMES_API_BASE or ` +
      `NEXT_PUBLIC_HERMES_API_BASE to be set. Neither was found. ` +
      "Failing fast to prevent ambiguous routing.",
    );
  }
}

export function getPlatformApiBase(): string {
  return (
    process.env.HERMES_API_BASE ||
    process.env.NEXT_PUBLIC_HERMES_API_BASE ||
    DEFAULT_PLATFORM_API_BASE
  );
}

export function getRuntimeApiBase(): string {
  return (
    process.env.MR_VISIT_JP_RUNTIME_BASE ||
    process.env.RUNTIME_API_BASE ||
    process.env.NEXT_PUBLIC_RUNTIME_API_BASE ||
    DEFAULT_DIRECT_RUNTIME_API_BASE
  );
}

function normalizeContextValue(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim();
  return normalized || null;
}

export function buildRuntimeProxyPath(
  path: string,
  context: RuntimeRequestContext = {}
): string {
  const url = new URL(path, "http://runtime-proxy.local");
  const authMode = getAuthMode();
  const orgId = normalizeContextValue(context.orgId);
  const viewerRole = normalizeContextValue(context.viewerRole);

  // When AUTH_MODE=mock or oidc, identity comes from server-side session,
  // not from client-supplied query params.
  if (orgId) {
    const normalizedOrgKey = orgId.toLowerCase();
    if ((authMode !== "mock" && authMode !== "oidc") || UNSCOPED_ORG_IDS.has(normalizedOrgKey)) {
      url.searchParams.set("org", orgId);
    }
  }
  if (authMode !== "mock" && authMode !== "oidc" && viewerRole) {
    url.searchParams.set("viewer", viewerRole);
  }

  return `${url.pathname}${url.search}`;
}

function parseRuntimePayload(rawText: string): unknown {
  if (!rawText) {
    return {};
  }
  try {
    return JSON.parse(rawText) as unknown;
  } catch {
    return { detail: rawText };
  }
}

export function runtimeErrorMessage(
  payload: unknown,
  fallback = "Request failed"
): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as RuntimeErrorPayload).detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
  }
  return fallback;
}

export function isMissingProgressSnapshotError(error: unknown): boolean {
  return (
    error instanceof Error &&
    error.message.includes("No progress snapshot for learner_id:")
  );
}

function extractTraceHeaders(
  headers: Headers
): Partial<Record<TraceResponseHeader, string>> {
  const extracted: Partial<Record<TraceResponseHeader, string>> = {};
  for (const headerName of TRACE_RESPONSE_HEADERS) {
    const headerValue = headers.get(headerName)?.trim();
    if (headerValue) {
      extracted[headerName] = headerValue;
    }
  }
  return extracted;
}

export async function readRuntimeJson<T>(
  input: RequestInfo | URL,
  init: RequestInit = {}
): Promise<T> {
  const response = await fetch(input, { ...init, cache: "no-store" });
  const payload = (await response.json()) as unknown;
  if (!response.ok) {
    throw new Error(runtimeErrorMessage(payload));
  }
  return payload as T;
}

export async function readOptionalProgressSnapshot(
  learnerId: string,
  context: RuntimeRequestContext = {}
): Promise<ProgressSnapshotResponse | null> {
  try {
    return await readRuntimeJson<ProgressSnapshotResponse>(
      buildRuntimeProxyPath(
        `/api/runtime/learners/${encodeURIComponent(learnerId)}/progress`,
        context
      )
    );
  } catch (error) {
    if (isMissingProgressSnapshotError(error)) {
      return null;
    }
    throw error;
  }
}

export async function readSessionSummary(
  sessionId: string,
  context: RuntimeRequestContext = {}
): Promise<SessionSummaryResponse> {
  return readRuntimeJson<SessionSummaryResponse>(
    buildRuntimeProxyPath(
      `/api/runtime/sessions/${encodeURIComponent(sessionId)}/summary`,
      context
    )
  );
}

export async function startRuntimeSession(
  learnerId: string,
  scenarioId: string,
  context: RuntimeRequestContext = {},
  locale?: string | null
): Promise<StartSessionResponse> {
  const normalizedLocale = typeof locale === "string" ? locale.trim() : "";
  return readRuntimeJson<StartSessionResponse>(
    buildRuntimeProxyPath("/api/runtime/sessions/start", context),
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        learner_id: learnerId,
        scenario_id: scenarioId,
        ...(normalizedLocale ? { locale: normalizedLocale } : {}),
      }),
    }
  );
}

export async function readOrganizationReports(
  organizationId: string,
  context: RuntimeRequestContext = {}
): Promise<OrganizationReportsResponse> {
  return readRuntimeJson<OrganizationReportsResponse>(
    buildRuntimeProxyPath(
      `/api/runtime/organizations/${encodeURIComponent(organizationId)}/reports`,
      context
    )
  );
}

export async function readEvaluationGates(
  context: RuntimeRequestContext = {}
): Promise<EvaluationGatesResponse> {
  return readRuntimeJson<EvaluationGatesResponse>(
    buildRuntimeProxyPath("/api/runtime/evaluation-gates", context)
  );
}

export async function proxyRuntime(
  path: string,
  init: Omit<RequestInit, "cache"> = {}
): Promise<RuntimeProxyResult> {
  const headers = new Headers(init.headers);
  if (!headers.has("content-type") && init.body) {
    headers.set("content-type", "application/json");
  }

  const requestWithBase = async (baseUrl: string): Promise<RuntimeProxyResult> => {
    const runtimeUrl = `${baseUrl}${path}`;
    const response = await fetch(runtimeUrl, {
      ...init,
      headers,
      cache: "no-store",
    });

    const payload = parseRuntimePayload(await response.text());
    return {
      status: response.status,
      payload,
      headers: extractTraceHeaders(response.headers),
      upstreamBase: baseUrl,
    };
  };

  const platformBase = getPlatformApiBase();
  const directRuntimeBase = getRuntimeApiBase();
  const deployEnv = getDeployEnv();
  const fallbackEnabled = deployEnv === "development" && directRuntimeBase !== platformBase;

  try {
    const result = await requestWithBase(platformBase);
    if (fallbackEnabled && [502, 503, 504].includes(result.status)) {
      console.warn(
        `[runtime-api] Hermes returned ${result.status}, ` +
        `falling back to direct runtime (${directRuntimeBase}). ` +
        `DEPLOY_ENV=${deployEnv}`,
      );
      return await requestWithBase(directRuntimeBase);
    }
    return result;
  } catch (error) {
    if (!fallbackEnabled) {
      throw error;
    }
    console.warn(
      `[runtime-api] Hermes unavailable, falling back to direct runtime (${directRuntimeBase}). ` +
      `DEPLOY_ENV=${deployEnv}`,
    );
    return await requestWithBase(directRuntimeBase);
  }
}

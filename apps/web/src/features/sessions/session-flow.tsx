"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";

import { AppIcon, ThumbnailArtwork, UserAvatar } from "@/components/app-graphics";
import { StartSessionErrorBanner } from "@/components/start-session-error-banner";
import { useAuth } from "@/lib/auth-context";
import {
  actionLabel,
  difficultyStars,
  eventLabel,
  finishReasonLabel,
  formatClock,
  formatDuration,
  formatTimestamp,
  phaseLabel,
  scenarioArtVariant,
  scorePercent,
  statusLabel,
  subskillLabel,
  timePressureLabel,
  turnProgressPercent,
} from "@/lib/mr-ui";
import {
  installOrgSkill,
  readSessionSummary,
  readRuntimeJson,
  startRuntimeSession,
  type CoachContinuity,
  type FinishSessionResponse,
  type ReviewResponse,
  type ScenarioSummary,
  type SendTurnResponse,
  type SessionEventEnvelope,
  type SessionEventsResponse,
  type SessionResponse,
  type SessionSummaryResponse,
  type TeachingPlanEvidence,
  type TurnSnapshot,
} from "@/lib/runtime-api";
import {
  canManageSkillInstall,
  isPermissionErrorMessage,
  parseStartSessionError,
  type StartSessionErrorDetails,
} from "@/lib/start-session-error";

type TurnRow = TurnSnapshot & {
  recommended_action?: string;
};

type SessionReviewPayload = ReviewResponse & {
  finished_at?: string;
};

type HistoricalHighlight = {
  turnIndex: number;
  turn: TurnRow | null;
  event: SessionEventEnvelope;
  label: string;
  actionText: string;
  diagnosisSummary: string | null;
};

type HistoricalSelectionContext = {
  finishReason?: string | null;
  highlightTurn?: number | null;
  scenarioFilter?: string | null;
  weakSkill?: string | null;
};

type SessionFlowProps = {
  sessionId: string;
  historicalSelection?: HistoricalSelectionContext;
  scenarioId: string | null;
};

const TURN_LOG_PREFIX = "mr_session_turns:";
const REVIEW_PREFIX = "mr_session_review:";
const PHASE_SEQUENCE = ["opening", "evidence", "discovery", "closing"];
type SessionLoadState = "loading" | "ready" | "failed";

function turnStorageKey(sessionId: string): string {
  return `${TURN_LOG_PREFIX}${sessionId}`;
}

function reviewStorageKey(sessionId: string): string {
  return `${REVIEW_PREFIX}${sessionId}`;
}

function eventContent(event: SessionEventEnvelope): Record<string, unknown> {
  return event.content ?? {};
}

function eventDirectorPhase(event: SessionEventEnvelope): string {
  const value = eventContent(event).director_phase;
  return typeof value === "string" ? value : "";
}

function eventDirectorEvents(event: SessionEventEnvelope): string[] {
  const value = eventContent(event).director_events;
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function eventRecommendedAction(event: SessionEventEnvelope): string | null {
  const value = eventContent(event).recommended_action;
  return typeof value === "string" && value.trim() ? value : null;
}

function eventTurnIndex(event: SessionEventEnvelope): number | null {
  const value = eventContent(event).turn_index;
  return typeof value === "number" ? value : null;
}

function openingDoctorPrompt(scenario: ScenarioSummary | null, t: (key: string, options?: Record<string, unknown>) => string): string {
  if (!scenario) {
    return t("session.doctorPrompt1");
  }
  if (scenario.persona_time_pressure === "high") {
    return t("session.doctorPrompt2");
  }
  if (scenario.persona_specialty.includes("oncology") || scenario.title.includes("学术")) {
    return t("session.doctorPrompt3");
  }
  return t("session.doctorPrompt4");
}

const WEAK_SKILL_SIGNALS: Record<
  string,
  { actions: string[]; events: string[]; phases: string[] }
> = {
  preparation: {
    actions: ["shorten_opening_and_get_permission"],
    events: ["carryover_opening_gap", "opening_overlong"],
    phases: ["opening"],
  },
  opening: {
    actions: ["shorten_opening_and_get_permission"],
    events: ["opening_missing_permission", "carryover_opening_gap", "time_pressure_not_respected"],
    phases: ["opening"],
  },
  profiling: {
    actions: ["ask_about_formulary_barrier"],
    events: ["formulary_barrier_not_explored", "prior_rejection_not_acknowledged"],
    phases: ["discovery"],
  },
  scientific_delivery: {
    actions: ["anchor_to_evidence_and_patient_segment", "cite_endpoint_safety_and_patient_segment"],
    events: [
      "evidence_not_addressed",
      "carryover_evidence_gap",
      "evidence_detail_missing",
      "evidence_dump_without_use_case",
      "unsupported_claim_without_evidence",
      "patient_use_case_not_defined",
    ],
    phases: ["evidence"],
  },
  need_discovery: {
    actions: ["ask_one_targeted_discovery_question"],
    events: ["discovery_question_missing", "carryover_need_discovery_gap"],
    phases: ["discovery"],
  },
  objection_handling: {
    actions: [
      "acknowledge_prior_rejection_and_offer_update",
      "switch_to_safety_followup",
      "ask_decision_criteria_before_comparison",
      "state_reporting_process_and_followup",
    ],
    events: [
      "prior_rejection_not_acknowledged",
      "no_new_relevance_after_rejection",
      "safety_reporting_not_started",
      "evidence_not_addressed",
      "unsupported_competitor_comparison",
      "followup_process_not_stated",
    ],
    phases: ["evidence", "safety"],
  },
  closing_followup: {
    actions: ["state_concrete_next_step", "state_micro_commitment_and_followup"],
    events: [
      "closing_next_step_missing",
      "carryover_followup_gap",
      "micro_commitment_missing",
      "max_turns_reached",
    ],
    phases: ["closing"],
  },
};

const SCENARIO_HIGHLIGHT_PREFERENCES: Record<
  string,
  { events: string[]; phases: string[] }
> = {
  adverse_event_followup_required: {
    events: ["safety_reporting_not_started", "safety_first_context"],
    phases: ["safety", "closing"],
  },
  busy_doctor_short_visit: {
    events: ["time_pressure_not_respected", "opening_missing_permission"],
    phases: ["opening", "closing"],
  },
  cautious_doctor_evidence_check: {
    events: ["evidence_not_addressed", "carryover_evidence_gap"],
    phases: ["evidence"],
  },
  formulary_restriction_negotiation: {
    events: ["formulary_barrier_not_explored"],
    phases: ["discovery", "closing"],
  },
  low_interest_doctor_intro_fail: {
    events: ["practical_relevance_not_established", "opening_missing_permission"],
    phases: ["opening", "discovery"],
  },
  new_product_adoption_barrier: {
    events: ["discovery_question_missing"],
    phases: ["discovery", "closing"],
  },
  revisit_after_prior_rejection: {
    events: ["prior_rejection_not_acknowledged", "no_new_relevance_after_rejection"],
    phases: ["discovery", "evidence"],
  },
  skeptical_doctor_competitor_pressure: {
    events: ["evidence_not_addressed", "carryover_evidence_gap"],
    phases: ["evidence", "closing"],
  },
};

function highlightScoreForWeakSkill(highlight: HistoricalHighlight, weakSkill: string): number {
  const signals = WEAK_SKILL_SIGNALS[weakSkill];
  if (!signals) {
    return 0;
  }
  let score = 0;
  const phase = eventDirectorPhase(highlight.event) || highlight.turn?.director_phase || "";
  const events = eventDirectorEvents(highlight.event);
  if (signals.phases.includes(phase)) {
    score += 3;
  }
  const recommendedAction = eventRecommendedAction(highlight.event);
  if (recommendedAction && signals.actions.includes(recommendedAction)) {
    score += 4;
  }
  if (events.some((item) => signals.events.includes(item))) {
    score += 5;
  }
  return score;
}

function highlightScoreForFinishReason(highlight: HistoricalHighlight, finishReason: string): number {
  const phase = eventDirectorPhase(highlight.event) || highlight.turn?.director_phase || "";
  const isClosing = phase === "closing";
  if (!finishReason) {
    return 0;
  }
  if (finishReason === "max_turns_reached") {
    return (isClosing ? 5 : 0) + (highlight.turnIndex > 0 ? highlight.turnIndex : 0);
  }
  if (finishReason === "learner_requested_finish") {
    return (isClosing ? 5 : 0) + highlight.turnIndex;
  }
  if (finishReason === "director_signaled_completion") {
    return (isClosing ? 6 : 0) + highlight.turnIndex;
  }
  return (isClosing ? 4 : 0) + highlight.turnIndex;
}

function highlightScoreForScenario(highlight: HistoricalHighlight, scenarioId: string): number {
  const preference = SCENARIO_HIGHLIGHT_PREFERENCES[scenarioId];
  if (!preference) {
    return 0;
  }
  let score = 0;
  const phase = eventDirectorPhase(highlight.event) || highlight.turn?.director_phase || "";
  const events = eventDirectorEvents(highlight.event);
  if (preference.phases.includes(phase)) {
    score += 3;
  }
  if (events.some((item) => preference.events.includes(item))) {
    score += 5;
  }
  return score;
}

function resolveHistoricalHighlightTurn(
  highlights: HistoricalHighlight[],
  context: HistoricalSelectionContext | undefined,
  sessionScenarioId: string | null,
): number | null {
  if (highlights.length === 0) {
    return null;
  }

  if (typeof context?.highlightTurn === "number") {
    const explicit = highlights.find((item) => item.turnIndex === context.highlightTurn);
    if (explicit) {
      return explicit.turnIndex;
    }
  }

  const scenarioId = context?.scenarioFilter ?? sessionScenarioId;
  const scored = highlights.map((highlight) => {
    let score = highlight.turnIndex;
    if (context?.weakSkill) {
      score += highlightScoreForWeakSkill(highlight, context.weakSkill) * 10;
    }
    if (context?.finishReason) {
      score += highlightScoreForFinishReason(highlight, context.finishReason) * 8;
    }
    if (scenarioId) {
      score += highlightScoreForScenario(highlight, scenarioId) * 4;
    }
    return { score, turnIndex: highlight.turnIndex };
  });

  scored.sort((left, right) => right.score - left.score || right.turnIndex - left.turnIndex);
  return scored[0]?.turnIndex ?? highlights.at(-1)?.turnIndex ?? null;
}

export function SessionFlow({ sessionId, scenarioId, historicalSelection }: SessionFlowProps) {
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const [isRoutePending, startRouteTransition] = useTransition();
  const turnInFlightRef = useRef(false);
  const finishInFlightRef = useRef(false);

  const [message, setMessage] = useState("");
  const [turns, setTurns] = useState<TurnRow[]>([]);
  const [status, setStatus] = useState<string>("initialized");
  const [scenario, setScenario] = useState<ScenarioSummary | null>(null);
  const [coachContinuity, setCoachContinuity] = useState<CoachContinuity | null>(null);
  const [learnerId, setLearnerId] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [startError, setStartError] = useState<StartSessionErrorDetails | null>(null);
  const [busy, setBusy] = useState<"idle" | "turn" | "finish">("idle");
  const [directorPhase, setDirectorPhase] = useState<string>("opening");
  const [directorEvents, setDirectorEvents] = useState<string[]>([]);
  const [recommendedAction, setRecommendedAction] = useState<string>("continue");
  const [sessionEvents, setSessionEvents] = useState<SessionEventEnvelope[]>([]);
  const [sessionReview, setSessionReview] = useState<SessionReviewPayload | null>(null);
  const [sessionReviewLoading, setSessionReviewLoading] = useState(false);
  const [startingScenarioId, setStartingScenarioId] = useState<string | null>(null);
  const [selectedHistoricalTurn, setSelectedHistoricalTurn] = useState<number | null>(null);
  const [loadState, setLoadState] = useState<SessionLoadState>("loading");
  const [summaryFallback, setSummaryFallback] = useState<SessionSummaryResponse | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [installingSkill, setInstallingSkill] = useState(false);

  useEffect(() => {
    const cached = localStorage.getItem(turnStorageKey(sessionId));
    if (!cached) {
      return;
    }
    try {
      const parsed = JSON.parse(cached) as {
        status?: string;
        turns?: TurnRow[];
        scenario?: ScenarioSummary;
        coach_continuity?: CoachContinuity;
        learner_id?: string;
        started_at?: string;
        message?: string;
        director_phase?: string;
        director_events?: string[];
        recommended_action?: string;
      };
      setStatus(parsed.status ?? "initialized");
      setTurns(Array.isArray(parsed.turns) ? parsed.turns : []);
      setScenario(parsed.scenario ?? null);
      setCoachContinuity(parsed.coach_continuity ?? null);
      setLearnerId(parsed.learner_id ?? null);
      setStartedAt(parsed.started_at ?? null);
      setMessage(typeof parsed.message === "string" ? parsed.message : "");
      const latestTurn = Array.isArray(parsed.turns) ? parsed.turns.at(-1) : null;
      setDirectorPhase(
        typeof parsed.director_phase === "string"
          ? parsed.director_phase
          : latestTurn?.director_phase ?? "opening"
      );
      setDirectorEvents(
        Array.isArray(parsed.director_events)
          ? parsed.director_events.filter((item): item is string => typeof item === "string")
          : latestTurn?.director_events ?? []
      );
      setRecommendedAction(
        typeof parsed.recommended_action === "string"
          ? parsed.recommended_action
          : latestTurn?.recommended_action ?? "continue"
      );
    } catch {
      localStorage.removeItem(turnStorageKey(sessionId));
    }
  }, [sessionId]);

  useEffect(() => {
    localStorage.setItem(
      turnStorageKey(sessionId),
      JSON.stringify({
        status,
        turns,
        scenario,
        coach_continuity: coachContinuity,
        learner_id: learnerId,
        started_at: startedAt,
        message,
        director_phase: directorPhase,
        director_events: directorEvents,
        recommended_action: recommendedAction,
      })
    );
  }, [
    coachContinuity,
    directorEvents,
    directorPhase,
    learnerId,
    message,
    recommendedAction,
    scenario,
    sessionId,
    startedAt,
    status,
    turns,
  ]);

  useEffect(() => {
    let active = true;
    const loadSession = async () => {
      setLoadState("loading");
      setError(null);
      setStartError(null);
      setSummaryFallback(null);
      try {
        const payload = await readRuntimeJson<SessionResponse>(`/api/runtime/sessions/${sessionId}`);
        if (!active) {
          return;
        }
        setStatus(payload.status);
        setTurns(Array.isArray(payload.turns) ? payload.turns : []);
        setScenario(payload.scenario);
        setCoachContinuity(payload.coach_continuity);
        setLearnerId(payload.learner_id);
        setStartedAt(payload.started_at);
        const latestTurn = payload.turns.at(-1);
        setDirectorPhase(latestTurn?.director_phase ?? "opening");
        setDirectorEvents(latestTurn?.director_events ?? []);
        setRecommendedAction((current) => current || "continue");
        setLoadState("ready");
      } catch (loadError) {
        const message = loadError instanceof Error ? loadError.message : "Unknown session load error";
        if (active && isPermissionErrorMessage(message)) {
          try {
            const summary = await readSessionSummary(sessionId);
            if (!active) {
              return;
            }
            setSummaryFallback(summary);
            setStatus(summary.status);
            setTurns([]);
            setScenario(null);
            setCoachContinuity(null);
            setLearnerId(null);
            setStartedAt(summary.started_at);
            setDirectorPhase("opening");
            setDirectorEvents([]);
            setRecommendedAction("continue");
            setLoadState("failed");
            setError(t("restricted.summaryOnly"));
            return;
          } catch {
            // Fall through to regular error handling if summary endpoint also fails.
          }
        }
        if (active) {
          setLoadState("failed");
          setError(message);
        }
      }
    };
    void loadSession();
    return () => {
      active = false;
    };
  }, [reloadKey, sessionId, t]);

  useEffect(() => {
    let active = true;
    const loadEvents = async () => {
      try {
        const data = await readRuntimeJson<SessionEventsResponse>(`/api/runtime/sessions/${sessionId}/events`);
        if (!active) {
          return;
        }
        const eventRows = Array.isArray(data.events) ? data.events : [];
        setSessionEvents(eventRows);
        const latestEvent = eventRows.filter((item) => item.type === "turn_processed").at(-1);
        if (!latestEvent) {
          return;
        }
        setDirectorPhase(eventDirectorPhase(latestEvent) || "opening");
        setDirectorEvents(eventDirectorEvents(latestEvent));
        setRecommendedAction(eventRecommendedAction(latestEvent) ?? "continue");
      } catch {
        if (active) {
          setSessionEvents([]);
        }
        return;
      }
    };
    void loadEvents();
    return () => {
      active = false;
    };
  }, [reloadKey, sessionId]);

  useEffect(() => {
    if (status !== "finalized") {
      setSessionReview(null);
      setSessionReviewLoading(false);
      return;
    }
    let active = true;
    const loadReview = async () => {
      setSessionReviewLoading(true);
      try {
        const data = await readRuntimeJson<ReviewResponse>(`/api/runtime/sessions/${sessionId}/review`);
        if (active) {
          setSessionReview(data);
        }
      } catch {
        const cached = localStorage.getItem(reviewStorageKey(sessionId));
        if (cached && active) {
          try {
            setSessionReview(JSON.parse(cached) as SessionReviewPayload);
          } catch {
            localStorage.removeItem(reviewStorageKey(sessionId));
            setSessionReview(null);
          }
        } else if (active) {
          setSessionReview(null);
        }
      } finally {
        if (active) {
          setSessionReviewLoading(false);
        }
      }
    };
    void loadReview();
    return () => {
      active = false;
    };
  }, [sessionId, status]);

  const sendTurn = async () => {
    if (
      !message.trim() ||
      busy !== "idle" ||
      loadState === "loading" ||
      status === "finalized" ||
      turnInFlightRef.current
    ) {
      return;
    }
    turnInFlightRef.current = true;
    setBusy("turn");
    setError(null);
    try {
      const trimmedMessage = message.trim();
      const payload = await readRuntimeJson<SendTurnResponse>(`/api/runtime/sessions/${sessionId}/turn`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: trimmedMessage }),
      });
      const nextTurn: TurnRow = {
        turn_index: payload.turn_index,
        user_message: trimmedMessage,
        doctor_reply: payload.doctor_reply,
        director_phase: payload.director.phase,
        director_events: payload.director.events,
        recommended_action: payload.director.recommended_action,
        created_at: new Date().toISOString(),
      };
      setTurns((prev) => [...prev, nextTurn]);
      setStatus(payload.status);
      setDirectorPhase(payload.director.phase);
      setDirectorEvents(payload.director.events);
      setRecommendedAction(payload.director.recommended_action);
      setMessage("");
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "Unknown send turn error");
    } finally {
      turnInFlightRef.current = false;
      setBusy("idle");
    }
  };

  const finishSession = async () => {
    if (
      busy !== "idle" ||
      loadState === "loading" ||
      turns.length === 0 ||
      status === "finalized" ||
      finishInFlightRef.current
    ) {
      return;
    }
    finishInFlightRef.current = true;
    setBusy("finish");
    setError(null);
    try {
      const payload = await readRuntimeJson<FinishSessionResponse>(
        `/api/runtime/sessions/${sessionId}/finish`,
        { method: "POST" }
      );
      setStatus(payload.status);
      localStorage.setItem(
        reviewStorageKey(sessionId),
        JSON.stringify({
          session_id: payload.session_id,
          scenario_id: payload.scenario_id,
          learner_id: payload.learner_id,
          started_at: startedAt,
          finished_at: new Date().toISOString(),
          finish_reason: payload.finish_reason,
          review: payload.review,
          scenario,
          coach_memory: payload.progress_snapshot?.coach_memory ?? null,
        })
      );
      startRouteTransition(() => {
        router.push(`/sessions/${sessionId}/review`);
      });
    } catch (finishError) {
      setError(finishError instanceof Error ? finishError.message : "Unknown finish session error");
    } finally {
      finishInFlightRef.current = false;
      setBusy("idle");
    }
  };

  const restartScenario = async () => {
    const targetScenarioId = scenario?.id ?? sessionReview?.scenario_id ?? scenarioId;
    if (!learnerId || !targetScenarioId) {
      return;
    }
    setStartingScenarioId(targetScenarioId);
    setError(null);
    setStartError(null);
    try {
      const data = await startRuntimeSession(
        learnerId,
        targetScenarioId,
        {
          orgId: user?.org_id ?? null,
          viewerRole: user?.role ?? null,
        },
        i18n.language
      );
      startRouteTransition(() => {
        router.push(`/sessions/${data.session_id}?scenario=${targetScenarioId}`);
      });
    } catch (startError) {
      const parsed = parseStartSessionError(startError, "Unknown scenario start error");
      setError(parsed.message);
      setStartError(parsed);
    } finally {
      setStartingScenarioId(null);
    }
  };

  const installMissingSkill = useCallback(async () => {
    if (!startError || startError.kind !== "skill_not_installed" || !startError.skillId) {
      return;
    }
    const targetOrgId = startError.orgId || user?.org_id || "local";
    setInstallingSkill(true);
    setError(null);
    try {
      await installOrgSkill(targetOrgId, startError.skillId, {
        ...(user?.learner_id ? { installed_by: user.learner_id } : {}),
      });
      setStartError(null);
      setError(t("marketplace.installSuccess"));
    } catch (installError) {
      const message = installError instanceof Error ? installError.message : t("marketplace.installFailed");
      setError(`${t("marketplace.installFailed")}: ${message}`);
    } finally {
      setInstallingSkill(false);
    }
  }, [startError, t, user?.learner_id, user?.org_id]);

  const progress = turnProgressPercent(turns.length, scenario?.max_turns ?? 8);
  const isClosing = directorPhase === "closing" || status === "awaiting_finish";
  const patience = Math.max(28, (scenario?.persona_time_pressure === "high" ? 70 : 86) - progress / 2);
  const interest = Math.max(42, 78 - directorEvents.length * 5 + (isClosing ? 8 : 0));
  const canSend =
    busy === "idle" &&
    loadState === "ready" &&
    status !== "finalized" &&
    message.trim().length > 0;
  const isHistoricalMode = status === "finalized";
  const displayScenarioTitle =
    sessionReview?.review.display_title ??
    coachContinuity?.scenario_title_override ??
    scenario?.title ??
    scenarioId ??
    sessionId;
  const completedAt = sessionReview?.finished_at ?? sessionReview?.updated_at ?? turns.at(-1)?.created_at ?? null;
  const sessionDuration = formatDuration(startedAt, completedAt);
  const scenarioFocusSubskills =
    scenario?.focus_subskills ??
    sessionReview?.scenario?.focus_subskills ??
    sessionReview?.review.priority_subskills ??
    [];
  const scenarioVariant = scenarioArtVariant(
    scenario?.id ?? sessionReview?.scenario_id ?? scenarioId ?? sessionId,
    scenarioFocusSubskills
  );
  const reviewNextActions =
    sessionReview?.review.coaching_feedback?.next_actions ??
    sessionReview?.coach_memory?.next_actions ??
    coachContinuity?.next_actions ??
    [];
  const reviewPrioritySubskills = sessionReview?.review.priority_subskills ?? [];
  const reviewStrengths = sessionReview?.review.strengths ?? [];
  const reviewComplianceFlags = sessionReview?.review.compliance_flags ?? [];
  const reviewDiagnosis = useMemo(() => sessionReview?.review.diagnosis?.primary ?? [], [sessionReview]);
  const frozenTeachingPlan = coachContinuity?.teaching_plan ?? null;
  const frozenTeachingPlanSnapshot = coachContinuity?.teaching_plan_snapshot ?? null;
  const restartScenarioTarget = scenario?.id ?? sessionReview?.scenario_id ?? scenarioId;
  const displayGoalItems = (scenario?.success_criteria ?? []).slice(0, 2);
  const continuityFocusSkills =
    coachContinuity?.carryover_focus_subskills?.length
      ? coachContinuity.carryover_focus_subskills
      : coachContinuity?.suggested_focus_subskills?.length
        ? coachContinuity.suggested_focus_subskills
        : frozenTeachingPlan?.focus_subskills ?? [];
  const continuitySummaryText =
    frozenTeachingPlan?.target_behavior ??
    coachContinuity?.summary ??
    t("session.noContinuityFocus");
  const directorGuidanceItems = [
    actionLabel(recommendedAction),
    ...directorEvents.slice(0, 2).map((item) => eventLabel(item)),
  ].filter((item, index, list) => item && list.indexOf(item) === index);
  const requestState = useMemo(() => {
    if (loadState === "loading" && turns.length === 0 && !scenario) {
      return {
        tone: "neutral" as const,
        label: t("session.requestLoading"),
        detail: t("session.requestLoadingDesc"),
      };
    }
    if (busy === "turn") {
      return {
        tone: "brand" as const,
        label: t("session.requestTurnSubmitting"),
        detail: t("session.requestTurnSubmittingDesc"),
      };
    }
    if (busy === "finish" || isRoutePending) {
      return {
        tone: "brand" as const,
        label: t("session.requestFinishing"),
        detail: t("session.requestFinishingDesc"),
      };
    }
    if (status === "finalized") {
      return {
        tone: "success" as const,
        label: t("session.requestFinalized"),
        detail: t("session.requestFinalizedDesc"),
      };
    }
    if (error) {
      return {
        tone: "danger" as const,
        label: t("session.requestFailed"),
        detail: error,
      };
    }
    return null;
  }, [busy, error, isRoutePending, loadState, scenario, status, t, turns.length]);
  const turnLookup = useMemo(() => {
    return new Map(turns.map((turn) => [turn.turn_index, turn]));
  }, [turns]);
  const historicalMoments = useMemo(() => {
    return sessionEvents
      .filter((event) => event.type === "turn_processed")
      .filter(
        (event) =>
          eventDirectorEvents(event).length > 0 ||
          Boolean(eventRecommendedAction(event))
      )
      .slice(-5);
  }, [sessionEvents]);
  const historicalHighlights = useMemo<HistoricalHighlight[]>(() => {
    return historicalMoments.map((event, index) => {
      const turnIndex = eventTurnIndex(event) ?? index + 1;
      const turn = turnLookup.get(turnIndex) ?? null;
      const directorEvents = eventDirectorEvents(event);
      const recommendedAction = eventRecommendedAction(event);
      const directorPhase = eventDirectorPhase(event) || turn?.director_phase || "opening";
      const label =
        directorEvents.length > 0
          ? eventLabel(directorEvents[0])
          : actionLabel(recommendedAction);
      return {
        turnIndex,
        turn,
        event,
        label,
        actionText: recommendedAction
          ? actionLabel(recommendedAction)
          : phaseLabel(directorPhase),
        diagnosisSummary: reviewDiagnosis[index]?.summary ?? null,
      };
    });
  }, [historicalMoments, reviewDiagnosis, turnLookup]);
  const highlightByTurn = useMemo(() => {
    return new Map(historicalHighlights.map((item) => [item.turnIndex, item]));
  }, [historicalHighlights]);
  const weakestSubskillRows = useMemo(() => {
    return Object.entries(sessionReview?.review.subskills ?? {})
      .sort(([, left], [, right]) => left.score - right.score)
      .slice(0, 5);
  }, [sessionReview]);

  useEffect(() => {
    if (!isHistoricalMode) {
      setSelectedHistoricalTurn(null);
      return;
    }
    const resolvedTurn = resolveHistoricalHighlightTurn(
      historicalHighlights,
      historicalSelection,
      scenario?.id ?? sessionReview?.scenario_id ?? null,
    );
    setSelectedHistoricalTurn((current) => {
      if (current !== null && historicalHighlights.some((item) => item.turnIndex === current)) {
        return current;
      }
      return resolvedTurn;
    });
  }, [historicalHighlights, historicalSelection, isHistoricalMode, scenario?.id, sessionReview?.scenario_id]);

  const focusHistoricalTurn = (turnIndex: number) => {
    setSelectedHistoricalTurn(turnIndex);
    const target = document.getElementById(`history-turn-${turnIndex}`);
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  if (isHistoricalMode) {
    return (
      <section className="dashboard-page">
        <div className="session-page-head">
          <Link className="back-link" href="/records">
            <AppIcon className="icon-sm" name="arrow-left" />
            <span>{t("session.backToRecords")}</span>
          </Link>
          <h1>{t("session.pageTitleHistory")}</h1>
          <div className="history-page-head-actions">
            <Link className="ghost-button" href={`/records/${sessionId}/review`}>
              {t("session.viewFullReview")}
            </Link>
            <button
              className="primary-button"
              disabled={!learnerId || !restartScenarioTarget || startingScenarioId !== null || isRoutePending}
              onClick={() => void restartScenario()}
              type="button"
            >
              <AppIcon className="icon-sm" name="play" />
              <span>{startingScenarioId || isRoutePending ? t("session.starting") : t("session.trainAgain")}</span>
            </button>
          </div>
        </div>

        {startError ? (
          <StartSessionErrorBanner
            canInstall={canManageSkillInstall(user?.role)}
            error={startError}
            installBusy={installingSkill}
            onInstall={() => {
              void installMissingSkill();
            }}
          />
        ) : error ? <div className="error-banner">{error}</div> : null}

        <section className="review-hero-card surface-card">
          <div className="review-hero-main">
            <ThumbnailArtwork className="history-hero-thumb" variant={scenarioVariant} />
            <div className="review-hero-copy history-hero-copy">
              <h2>{displayScenarioTitle}</h2>
              <div className="review-meta-row">
                <span>
                  <AppIcon className="icon-sm" name="calendar" />
                  {t("session.completionTime")}{formatTimestamp(completedAt)}
                </span>
                <span>
                  <AppIcon className="icon-sm" name="clock" />
                  {t("session.durationLabel")}{sessionDuration}
                </span>
                <span>
                  <AppIcon className="icon-sm" name="doctor" />
                  {scenario?.persona_label ?? t("session.unlabeledPersona")}
                </span>
              </div>
              <div className="history-hero-focus">
                <span className="section-chip">
                  {difficultyStars(scenario?.difficulty ?? sessionReview?.scenario?.difficulty ?? "medium")}
                </span>
                <span className="section-chip">
                  {timePressureLabel(scenario?.persona_time_pressure)}
                </span>
                {scenarioFocusSubskills.slice(0, 3).map((skill) => (
                  <span className="section-chip" key={`focus-${skill}`}>
                    {subskillLabel(skill)}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="review-hero-stats">
            <article>
              <span>{t("session.totalScore")}</span>
              <strong>{sessionReview?.review.overall_score ?? "-"} / 100</strong>
            </article>
            <article>
              <span>{t("session.finishMethod")}</span>
              <strong>{finishReasonLabel(sessionReview?.finish_reason)}</strong>
            </article>
            <article>
              <span>{t("session.mainWeakness")}</span>
              <div className="tag-list">
                {reviewPrioritySubskills.slice(0, 2).map((skill) => (
                  <span className="warning-tag" key={`priority-${skill}`}>
                    {subskillLabel(skill)}
                  </span>
                ))}
                {reviewPrioritySubskills.length === 0 ? <span className="section-chip">{t("session.syncingReview")}</span> : null}
              </div>
            </article>
            <article>
              <span>{t("session.nextSteps")}</span>
              <strong>{reviewNextActions[0] ?? t("session.viewReviewForAdvice")}</strong>
            </article>
          </div>
        </section>

        <div className="history-layout">
          <div className="history-main-stack">
            <section className="panel surface-card history-panel">
              <div className="section-header">
                <div className="section-title">
                  <AppIcon className="icon-md icon-brand" name="doc" />
                  <span>{t("session.historyChat")}</span>
                </div>
                <span className="session-status-pill history-mode-pill">
                  <span className="status-dot" />
                  {t("session.readOnlyHistory")}
                </span>
              </div>

              <div className="chat-scroll history-chat-scroll">
                <article className="chat-row">
                  <UserAvatar className="chat-avatar" compact />
                  <div className="chat-content">
                    <div className="chat-role">医生</div>
                    <div className="chat-bubble doctor">{openingDoctorPrompt(scenario, t)}</div>
                    <small>{formatClock(startedAt)}</small>
                  </div>
                </article>

                {turns.map((turn) => (
                  <div
                    className={`chat-turn-block${highlightByTurn.has(turn.turn_index) ? " is-key-turn" : ""}${
                      selectedHistoricalTurn === turn.turn_index ? " is-selected" : ""
                    }`}
                    id={`history-turn-${turn.turn_index}`}
                    key={turn.turn_index}
                  >
                    {highlightByTurn.has(turn.turn_index) ? (
                      <div className="history-turn-focus">
                        <div className="history-turn-focus-head">
                          <div className="timeline-turn-tag">Turn {turn.turn_index}</div>
                          <button
                            className="section-link"
                            onClick={() => focusHistoricalTurn(turn.turn_index)}
                            type="button"
                          >
                            定位到此
                          </button>
                        </div>
                        <div className="history-turn-focus-meta">
                          <span className="section-chip">{highlightByTurn.get(turn.turn_index)?.label}</span>
                          <span className="section-chip">{highlightByTurn.get(turn.turn_index)?.actionText}</span>
                        </div>
                      </div>
                    ) : null}

                    <article className="chat-row self">
                      <div className="chat-content self">
                        <div className="chat-role">{t("session.roleYou")}</div>
                        <div className="chat-bubble self">{turn.user_message}</div>
                        <small>{formatClock(turn.created_at)}</small>
                      </div>
                      <UserAvatar className="chat-avatar" compact />
                    </article>

                    <article className="chat-row">
                      <UserAvatar className="chat-avatar" compact />
                      <div className="chat-content">
                        <div className="chat-role">{t("session.roleDoctor")}</div>
                        <div className="chat-bubble doctor">{turn.doctor_reply}</div>
                        <small>{formatClock(turn.created_at)}</small>
                      </div>
                    </article>

                    {turn.director_events.length > 0 ? (
                      <div className="event-banner">
                        <AppIcon className="icon-sm icon-brand" name="lightbulb" />
                        <strong>{t("session.eventLabel")}</strong>
                        <span>{eventLabel(turn.director_events[0])}</span>
                        <small>{formatClock(turn.created_at)}</small>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </section>

            <section className="panel surface-card history-panel">
              <div className="section-header">
                <div className="section-title">
                  <AppIcon className="icon-md icon-brand" name="star" />
                  <span>{t("session.keyNodeTimeline")}</span>
                </div>
                <span className="section-chip">{t("session.tagCount", { count: historicalMoments.length })}</span>
              </div>
              <div className="timeline-list">
                {historicalMoments.length === 0 ? (
                  <div className="placeholder-inline">{t("session.noKeyNodesYet")}</div>
                ) : (
                  historicalHighlights.map((highlight, index) => {
                    return (
                      <article className="timeline-row" key={`${highlight.turnIndex}-${index}`}>
                        <div className={`timeline-dot${index === historicalHighlights.length - 1 ? " success" : " warn"}`} />
                        <button
                          className={`timeline-card timeline-card-button${
                            selectedHistoricalTurn === highlight.turnIndex ? " is-selected" : ""
                          }`}
                          onClick={() => focusHistoricalTurn(highlight.turnIndex)}
                          type="button"
                        >
                          <div className="timeline-turn-tag">Turn {highlight.turnIndex}</div>
                          <div className="history-highlight-grid">
                            <div className="history-quote-card self">
                              <span className="history-speaker-tag self">{t("session.userOriginal")}</span>
                              <p>{highlight.turn?.user_message ?? t("session.userQuoteMissing")}</p>
                            </div>
                            <div className="history-quote-card doctor">
                              <span className="history-speaker-tag doctor">{t("session.doctorOriginal")}</span>
                              <p>{highlight.turn?.doctor_reply ?? t("session.doctorQuoteMissing")}</p>
                            </div>
                            <div className="timeline-side-note">
                              <span>{t("session.directorTag")}</span>
                              <strong>{highlight.label}</strong>
                              <small>{highlight.actionText}</small>
                              <p>{highlight.diagnosisSummary ?? t("session.markedForReview")}</p>
                            </div>
                          </div>
                        </button>
                      </article>
                    );
                  })
                )}
              </div>
            </section>
          </div>

          <aside className="history-side-stack">
            <section className="panel surface-card history-panel">
              <div className="section-header">
                <div className="section-title">
                  <AppIcon className="icon-md icon-brand" name="clipboard" />
                  <span>{t("session.scenarioInfo")}</span>
                </div>
              </div>
              <div className="info-card-stack">
                <article className="info-tile">
                  <div className="info-tile-head">
                    <strong>{t("session.recordStatus")}</strong>
                    <span className="status-tag">{statusLabel(status)}</span>
                  </div>
                  <div className="info-status-list">
                    <p>{t("session.startTime")}{formatTimestamp(startedAt)}</p>
                    <p>{t("session.completionTime")}{formatTimestamp(completedAt)}</p>
                    <p>{t("session.rounds", { count: turns.length })}</p>
                  </div>
                </article>
                <article className="info-tile">
                  <strong>{t("session.doctorPersona")}</strong>
                  <p>{scenario?.persona_label ?? "-"}</p>
                  <small>{scenario?.persona_specialty ?? t("session.hospitalMissing")}</small>
                </article>
                <article className="info-tile">
                  <strong>{t("session.currentGoal")}</strong>
                  <ul className="bullet-list">
                    {(scenario?.success_criteria ?? []).slice(0, 3).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                    {(scenario?.success_criteria ?? []).length === 0 ? <li>{t("session.noGoalDesc")}</li> : null}
                  </ul>
                </article>
                <article className="info-tile">
                  <strong>{t("session.continuitySummary")}</strong>
                  <p>{coachContinuity?.summary ?? sessionReview?.coach_memory?.summary ?? t("session.syncingSummary")}</p>
                </article>
                <article className="info-tile">
                  <strong>{t("progress.activeTeachingPlan")}</strong>
                  {frozenTeachingPlan ? (
                    <div className="info-status-list">
                      <p>{t("progress.targetBehavior")}{frozenTeachingPlan.target_behavior}</p>
                      <p>{t("progress.successCriterion")}{frozenTeachingPlan.success_criterion}</p>
                      {frozenTeachingPlan.version ? (
                        <p>
                          {t("progress.planVersion")} v{frozenTeachingPlan.version}
                          {frozenTeachingPlanSnapshot?.frozen_at
                            ? ` · ${t("progress.planFrozenAt")}${formatTimestamp(frozenTeachingPlanSnapshot.frozen_at)}`
                            : ""}
                        </p>
                      ) : null}
                      <div className="tag-list">
                        {frozenTeachingPlan.focus_subskills.map((skill: string) => (
                          <span className="mini-tag" key={skill}>{subskillLabel(skill)}</span>
                        ))}
                      </div>
                      {Array.isArray(frozenTeachingPlan.prior_evidence) && frozenTeachingPlan.prior_evidence.length > 0 ? (
                        <ul className="bullet-list">
                          {frozenTeachingPlan.prior_evidence.slice(0, 2).map((item: TeachingPlanEvidence, index: number) => (
                            <li key={`${item.summary ?? "evidence"}-${index}`}>
                              {item.summary}
                              {item.scenario_title ? ` · ${item.scenario_title}` : ""}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ) : (
                    <p>{t("progress.noPlan")}</p>
                  )}
                </article>
              </div>
            </section>

            <section className="panel surface-card history-panel">
              <div className="section-header">
                <div className="section-title">
                  <AppIcon className="icon-md icon-brand" name="lightbulb" />
                  <span>{t("session.reviewSummary")}</span>
                </div>
              </div>
              {sessionReviewLoading && !sessionReview ? (
                <div className="placeholder-inline">{t("session.syncingReviewResult")}</div>
              ) : (
                <div className="history-summary-stack">
                  <div className="history-side-block">
                    <strong>{t("session.mainConclusion")}</strong>
                    <ul className="bullet-list">
                      {reviewDiagnosis.slice(0, 3).map((item, index) => (
                        <li key={`diag-${index}`}>{item.summary ?? t("session.defaultConclusion")}</li>
                      ))}
                      {reviewDiagnosis.length === 0 ? <li>{t("session.conclusionInReview")}</li> : null}
                    </ul>
                  </div>
                  <div className="history-side-block">
                    <strong>{t("session.nextSteps")}</strong>
                    <ul className="bullet-list">
                      {reviewNextActions.slice(0, 3).map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                      {reviewNextActions.length === 0 ? <li>{t("session.suggestAdviceInReview")}</li> : null}
                    </ul>
                  </div>
                  <div className="history-side-block">
                    <strong>{t("session.strengths")}</strong>
                    <ul className="bullet-list">
                      {reviewStrengths.slice(0, 3).map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                      {reviewStrengths.length === 0 ? <li>{t("session.strengthSummaryInReview")}</li> : null}
                    </ul>
                  </div>
                </div>
              )}
            </section>

            <section className="panel surface-card history-panel">
              <div className="section-header">
                <div className="section-title">
                  <AppIcon className="icon-md icon-brand" name="chart" />
                  <span>{t("session.subskillSnapshot")}</span>
                </div>
              </div>
              <div className="history-skill-stack">
                {weakestSubskillRows.length === 0 ? (
                  <div className="placeholder-inline">{t("session.scoreInReview")}</div>
                ) : (
                  weakestSubskillRows.map(([skillId, item]) => {
                    const percent = scorePercent(item.score);
                    return (
                      <div className="history-skill-row" key={skillId}>
                        <div className="history-skill-head">
                          <strong>{subskillLabel(skillId)}</strong>
                          <span>{percent}%</span>
                        </div>
                        <div className={`progress-bar compact${percent < 55 ? " warn" : ""}`}>
                          <span style={{ width: `${percent}%` }} />
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </section>

            <section className="panel surface-card history-panel">
              <div className="section-header">
                <div className="section-title">
                  <AppIcon className="icon-md icon-brand" name="shield" />
                  <span>{t("session.compliance")}</span>
                </div>
              </div>
              <ul className="bullet-list">
                {reviewComplianceFlags.slice(0, 3).map((item, index) => (
                  <li key={`flag-${index}`}>{item.summary ?? t("session.checkFullReview")}</li>
                ))}
                {reviewComplianceFlags.length === 0 ? <li>{t("session.noNewCompliance")}</li> : null}
              </ul>
            </section>
          </aside>
        </div>
      </section>
    );
  }

  if (loadState === "loading" && turns.length === 0 && !scenario) {
    return (
      <section className="dashboard-page">
        <div className="placeholder-block surface-card">
          <strong>{t("session.requestLoading")}</strong>
          <p>{t("session.requestLoadingDesc")}</p>
        </div>
      </section>
    );
  }

  if (loadState === "failed" && turns.length === 0 && !scenario) {
    if (summaryFallback) {
      return (
        <section className="dashboard-page">
          <div className="placeholder-block surface-card">
            <strong>{t("restricted.summaryOnly")}</strong>
            <p>{summaryFallback.detail || t("restricted.sessionTranscript")}</p>
            <div className="info-card-stack" style={{ marginTop: 12 }}>
              <article className="info-tile">
                <strong>{t("session.scenarioLabel")}{summaryFallback.scenario_id}</strong>
                <p>{t("session.recordStatus")}{statusLabel(summaryFallback.status)}</p>
                <small>{t("session.rounds", { count: summaryFallback.turn_count })}</small>
                {typeof summaryFallback.overall_score === "number" ? (
                  <small>{t("session.totalScore")}{summaryFallback.overall_score} / 100</small>
                ) : null}
              </article>
            </div>
            <div className="placeholder-actions">
              <Link className="ghost-button" href="/records">
                {t("session.backToRecords")}
              </Link>
              {summaryFallback.review_ready ? (
                <Link className="primary-button" href={`/records/${sessionId}/review`}>
                  {t("session.viewFullReview")}
                </Link>
              ) : (
                <button
                  className="primary-button"
                  onClick={() => setReloadKey((value) => value + 1)}
                  type="button"
                >
                  <AppIcon className="icon-sm" name="refresh" />
                  <span>{t("session.retryLoad")}</span>
                </button>
              )}
            </div>
          </div>
        </section>
      );
    }
    return (
      <section className="dashboard-page">
        <div className="placeholder-block surface-card">
          <strong>{t("session.requestFailed")}</strong>
          <p>{error ?? t("session.requestFailedDesc")}</p>
          <div className="placeholder-actions">
            <button
              className="primary-button"
              onClick={() => setReloadKey((value) => value + 1)}
              type="button"
            >
              <AppIcon className="icon-sm" name="refresh" />
              <span>{t("session.retryLoad")}</span>
            </button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="dashboard-page">
      <div className="session-page-head">
        <Link className="back-link" href="/scenarios">
          <AppIcon className="icon-sm" name="arrow-left" />
          <span>{t("session.backToScenarios")}</span>
        </Link>
        <h1>{t("session.pageTitleSession")}</h1>
        <div className="session-head-spacer" />
      </div>

      {startError ? (
        <StartSessionErrorBanner
          canInstall={canManageSkillInstall(user?.role)}
          error={startError}
          installBusy={installingSkill}
          onInstall={() => {
            void installMissingSkill();
          }}
        />
      ) : error ? <div className="error-banner">{error}</div> : null}

      <div className="session-layout">
        <aside className="session-side">
          <section className="panel surface-card">
            <div className="section-header">
              <div className="section-title">
                <AppIcon className="icon-md icon-brand" name="clipboard" />
                <span>场景信息</span>
              </div>
            </div>
            <div className="info-card-stack">
              <article className="info-tile">
                <strong>{t("session.scenarioTitle")}</strong>
                <p>{displayScenarioTitle}</p>
              </article>
              <article className="info-tile">
                <strong>{t("session.hospitalDept")}</strong>
                <p>{t("session.hospitalMissing")}</p>
                <small>{scenario?.persona_specialty ?? "-"}</small>
              </article>
              <article className="info-tile">
                <strong>{t("session.doctorType")}</strong>
                <p>{scenario?.persona_label ?? "-"}</p>
              </article>
              <article className="info-tile">
                <strong>{t("session.currentGoal")}</strong>
                <p>{scenario?.success_criteria.slice(0, 2).join(" / ") || t("session.noGoalDesc")}</p>
              </article>
              <article className="info-tile">
                <strong>{t("session.currentFocusSkills")}</strong>
                <ul className="bullet-list">
                  {(scenario?.focus_subskills ?? []).map((skill) => (
                    <li key={skill}>{subskillLabel(skill)}</li>
                  ))}
                </ul>
              </article>
              {coachContinuity?.carryover_focus_subskills && coachContinuity.carryover_focus_subskills.length > 0 && (
                <article className="info-tile highlight-tile">
                  <strong>{t("session.carryoverFocus")}</strong>
                  <div className="tag-list">
                    {coachContinuity.carryover_focus_subskills.map((skill) => (
                      <span className="warning-tag" key={`carryover-${skill}`}>
                        {subskillLabel(skill)}
                      </span>
                    ))}
                  </div>
                </article>
              )}
              <article className="info-tile">
                <div className="info-tile-head">
                  <strong>{t("session.scenarioStatus")}</strong>
                  <span className="status-tag">{statusLabel(status)}</span>
                </div>
                <div className="info-status-list">
                  <p>{t("session.startTime")}{formatClock(startedAt)}</p>
                  <p>{t("session.roundIndex", { count: Math.max(turns.length, 1) })}</p>
                  <p>{t("session.progress")}{progress}%</p>
                </div>
                <div className="progress-bar compact">
                  <span style={{ width: `${progress}%` }} />
                </div>
              </article>
            </div>
          </section>
        </aside>

        <section className="panel surface-card session-center">
          <div className="section-header">
            <div className="section-title">
              <span>{t("session.scenarioLabel")}{displayScenarioTitle}</span>
            </div>
            <div className="session-header-statuses">
              {requestState ? (
                <span className={`session-status-pill request-pill is-${requestState.tone}`}>
                  <span className="status-dot" />
                  {requestState.label}
                </span>
              ) : null}
              <span className="session-status-pill">
                <span className="status-dot" />
                {statusLabel(status)}
              </span>
            </div>
          </div>

          <div className="live-session-strip">
            <article className="live-context-card">
              <div className="live-context-head">
                <AppIcon className="icon-sm icon-brand" name="target" />
                <strong>{t("session.liveGoal")}</strong>
              </div>
              {displayGoalItems.length > 0 ? (
                <ul className="bullet-list compact-bullets">
                  {displayGoalItems.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p>{t("session.noGoalDesc")}</p>
              )}
            </article>

            <article className="live-context-card">
              <div className="live-context-head">
                <AppIcon className="icon-sm icon-brand" name="doctor" />
                <strong>{t("session.liveDoctorPersona")}</strong>
              </div>
              <p>{scenario?.persona_label ?? "-"}</p>
              <div className="tag-list">
                <span className="section-chip">{timePressureLabel(scenario?.persona_time_pressure)}</span>
                {scenario?.persona_specialty ? (
                  <span className="section-chip">{scenario.persona_specialty}</span>
                ) : null}
              </div>
            </article>

            <article className="live-context-card">
              <div className="live-context-head">
                <AppIcon className="icon-sm icon-brand" name="spark" />
                <strong>{t("session.liveContinuityFocus")}</strong>
              </div>
              <p>{continuitySummaryText}</p>
              {continuityFocusSkills.length > 0 ? (
                <div className="tag-list">
                  {continuityFocusSkills.slice(0, 3).map((skill) => (
                    <span className="warning-tag" key={`live-focus-${skill}`}>
                      {subskillLabel(skill)}
                    </span>
                  ))}
                </div>
              ) : null}
            </article>

            <article className="live-context-card emphasis-card">
              <div className="live-context-head">
                <AppIcon className="icon-sm icon-brand" name="lightbulb" />
                <strong>{t("session.liveDirectorGuidance")}</strong>
              </div>
              <p>{actionLabel(recommendedAction)}</p>
              {directorGuidanceItems.length > 0 ? (
                <div className="tag-list">
                  {directorGuidanceItems.slice(0, 3).map((item) => (
                    <span className="section-chip" key={item}>{item}</span>
                  ))}
                </div>
              ) : null}
              {requestState ? (
                <small>{requestState.detail}</small>
              ) : (
                <small>{t("session.requestReadyDesc")}</small>
              )}
            </article>
          </div>

          <div className="chat-scroll">
            {turns.length === 0 ? (
              <article className="chat-row">
                <UserAvatar className="chat-avatar" compact />
                <div className="chat-content">
                  <div className="chat-role">{t("session.roleDoctor")}</div>
                  <div className="chat-bubble doctor">{openingDoctorPrompt(scenario, t)}</div>
                  <small>{formatClock(startedAt)}</small>
                </div>
              </article>
            ) : null}

            {turns.map((turn) => (
              <div className="chat-turn-block" key={turn.turn_index}>
                <article className="chat-row self">
                  <div className="chat-content self">
                    <div className="chat-role">{t("session.roleYou")}</div>
                    <div className="chat-bubble self">{turn.user_message}</div>
                    <small>{formatClock(turn.created_at)}</small>
                  </div>
                  <UserAvatar className="chat-avatar" compact />
                </article>

                <article className="chat-row">
                  <UserAvatar className="chat-avatar" compact />
                  <div className="chat-content">
                    <div className="chat-role">{t("session.roleDoctor")}</div>
                    <div className="chat-bubble doctor">{turn.doctor_reply}</div>
                    <small>{formatClock(turn.created_at)}</small>
                  </div>
                </article>

                {turn.director_events.length > 0 ? (
                  <div className="event-banner">
                    <AppIcon className="icon-sm icon-brand" name="lightbulb" />
                    <strong>{t("session.eventLabel")}</strong>
                    <span>{eventLabel(turn.director_events[0])}</span>
                    <small>{formatClock(turn.created_at)}</small>
                  </div>
                ) : null}
              </div>
            ))}
          </div>

          <div className="composer-card">
            <div className="composer-row">
              <textarea
                className="composer-input"
                disabled={busy !== "idle" || status === "finalized" || loadState === "loading"}
                onChange={(event) => setMessage(event.target.value)}
                placeholder={t("session.placeholderInput")}
                rows={3}
                value={message}
              />
              <button className="primary-button send-button" disabled={!canSend} onClick={() => void sendTurn()} type="button">
                <AppIcon className="icon-sm" name="send" />
                <span>{busy === "turn" ? t("session.sending") : t("session.send")}</span>
              </button>
            </div>
            <button
              className="ghost-button finish-button"
              disabled={busy !== "idle" || loadState !== "ready" || turns.length === 0 || status === "finalized"}
              onClick={() => void finishSession()}
              type="button"
            >
              {busy === "finish" || isRoutePending ? t("session.finishing") : t("session.finishSession")}
            </button>
          </div>
        </section>

        <aside className="session-side">
          <section className="panel surface-card">
            <div className="section-header">
              <div className="section-title">
                <AppIcon className="icon-md icon-brand" name="lightbulb" />
                <span>{t("session.assistTitle")}</span>
              </div>
            </div>

            <article className="assist-card">
              <strong>{t("session.currentPhase")}</strong>
              <div className="phase-steps">
                {PHASE_SEQUENCE.map((phase) => (
                  <div className="phase-step" key={phase}>
                    <span className={`phase-dot${directorPhase === phase ? " is-active" : ""}`} />
                    <small>{phaseLabel(phase)}</small>
                  </div>
                ))}
              </div>
            </article>

            <article className="assist-card">
              <strong>{t("session.keyReminders")}</strong>
              <ul className="bullet-list">
                {(coachContinuity?.next_actions ?? []).slice(0, 4).map((item) => (
                  <li key={item}>{item}</li>
                ))}
                {directorEvents.slice(0, 2).map((item) => (
                  <li key={item}>{eventLabel(item)}</li>
                ))}
              </ul>
            </article>

            <article className="assist-card">
              <strong>{t("session.lightweightHints")}</strong>
              <p>{actionLabel(recommendedAction)}</p>
            </article>

            <article className="assist-card">
              <strong>{t("session.realTimeStatus")}</strong>
              <div className="status-meter">
                <span>{t("session.interest")}</span>
                <div className="progress-bar compact">
                  <span style={{ width: `${interest}%` }} />
                </div>
                <strong>{Math.round(interest)}%</strong>
              </div>
              <div className="status-meter">
                <span>{t("session.patience")}</span>
                <div className="progress-bar compact">
                  <span style={{ width: `${patience}%` }} />
                </div>
                <strong>{Math.round(patience)}%</strong>
              </div>
              <div className="status-row">
                <span>{t("session.isClosing")}</span>
                <strong>{isClosing ? t("session.yes") : t("session.no")}</strong>
              </div>
            </article>

            <article className="assist-card">
              <strong>{t("session.availableDocs")}</strong>
              <div className="doc-links">
                {[
                  t("session.docCore"),
                  t("session.docClinical"),
                  t("session.docCompetitor"),
                  t("session.docFaq"),
                ].map((item) => (
                  <button className="doc-link-row" key={item} type="button">
                    <div>
                      <AppIcon className="icon-sm icon-brand" name="doc" />
                      <span>{item}</span>
                    </div>
                    <AppIcon className="icon-sm" name="arrow-right" />
                  </button>
                ))}
              </div>
            </article>
          </section>
        </aside>
      </div>
    </section>
  );
}

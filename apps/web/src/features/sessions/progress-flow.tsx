"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";

import { AppIcon, ThumbnailArtwork } from "@/components/app-graphics";
import { StartSessionErrorBanner } from "@/components/start-session-error-banner";
import {
  DEFAULT_SUBSKILL_ORDER,
  formatTimestamp,
  scenarioArtVariant,
  scorePercent,
  sparklinePoints,
  subskillLabel,
} from "@/lib/mr-ui";
import {
  type CurriculumProgress as RuntimeCurriculumProgress,
  fetchCrossSkillDashboard,
  installOrgSkill,
  type CrossSkillDashboardEntry,
  type PracticePathEntry,
  readOptionalProgressSnapshot,
  type ScenarioRecommendation,
  type SkillWorld,
  startRuntimeSession,
  type ProgressSnapshotResponse,
  type TeachingPlan,
} from "@/lib/runtime-api";
import {
  canManageSkillInstall,
  parseStartSessionError,
  type StartSessionErrorDetails,
} from "@/lib/start-session-error";

type ProgressFlowProps = {
  initialLearnerId: string;
  orgId?: string | null;
  viewerRole?: string | null;
};

type SkillRow = {
  skillId: string;
  payload: ProgressSnapshotResponse["subskills"][string] | null;
};

const REVIEW_PRIORITY: Record<string, number> = {
  due: 0,
  focus_now: 1,
  soon: 2,
  maintain: 3,
};

function masteryBadgeTone(status?: string | null): "error" | "warn" | "brand" | "success" {
  switch (status) {
    case "mastered":
      return "success";
    case "stable":
      return "brand";
    case "improving":
      return "warn";
    default:
      return "error";
  }
}

function reviewBadgeTone(status?: string | null): "error" | "warn" | "brand" | "success" {
  switch (status) {
    case "due":
      return "error";
    case "soon":
    case "focus_now":
      return "warn";
    default:
      return "success";
  }
}

function formatReviewSchedule(
  t: ReturnType<typeof useTranslation>["t"],
  reviewStatus?: string | null,
  nextReviewInSessions?: number | null
): string {
  if (reviewStatus === "due" || reviewStatus === "focus_now") {
    return String(t("progress.reviewNow"));
  }
  if (typeof nextReviewInSessions === "number") {
    return String(t("progress.reviewInSessions", { count: Math.max(1, nextReviewInSessions) }));
  }
  if (reviewStatus) {
    return String(t(`progress.reviewStatus.${reviewStatus}`));
  }
  return String(t("progress.reviewStatus.maintain"));
}

function ActiveTeachingPlanPanel({ plan }: { plan?: TeachingPlan | null }) {
  const { t } = useTranslation();
  if (!plan) return null;

  return (
    <section className="panel surface-card teaching-plan-panel">
      <div className="section-header">
        <div className="section-title">
          <AppIcon className="icon-md icon-brand" name="target" />
          <span>{t("progress.activeTeachingPlan")}</span>
        </div>
      </div>
      <div className="teaching-plan-body">
        <div className="teaching-plan-main">
          <div className="plan-item">
            <span className="label">{t("progress.planReason")}</span>
            <p>{plan.reason}</p>
          </div>
          <div className="plan-item">
            <span className="label">{t("progress.targetBehavior")}</span>
            <p>{plan.target_behavior}</p>
          </div>
          <div className="plan-item">
            <span className="label">{t("progress.successCriterion")}</span>
            <p>{plan.success_criterion}</p>
          </div>
          {Array.isArray(plan.prior_evidence) && plan.prior_evidence.length > 0 ? (
            <div className="plan-item">
              <span className="label">{t("progress.priorEvidence")}</span>
              <ul className="bullet-list">
                {plan.prior_evidence.slice(0, 2).map((item, index: number) => (
                  <li key={`${item.summary ?? "evidence"}-${index}`}>
                    {item.summary}
                    {item.scenario_title ? ` · ${item.scenario_title}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {plan.version ? (
            <div className="plan-item">
              <span className="label">{t("progress.planVersion")}</span>
              <p>v{plan.version}</p>
            </div>
          ) : null}
        </div>
        <div className="plan-focus-skills">
          {plan.focus_subskills?.map((skill: string) => (
            <span className="skill-tag" key={skill}>
              {subskillLabel(skill)}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function CurriculumStagePanel({
  curriculum,
}: {
  curriculum?: RuntimeCurriculumProgress | null;
}) {
  const { t } = useTranslation();
  if (!curriculum) return null;

  const isCompleted = curriculum.status === "completed";

  return (
    <section
      className={`panel surface-card curriculum-stage-panel${isCompleted ? " success" : ""}`}
    >
      <div className="section-header">
        <div className="section-title">
          <AppIcon className="icon-md icon-brand" name="target" />
          <span>{t("progress.curriculumStage")}</span>
        </div>
        <span className={`status-badge ${isCompleted ? "success" : "warn"}`}>
          {t(isCompleted ? "progress.curriculumCompleted" : "progress.curriculumInProgress")}
        </span>
      </div>
      <div className="curriculum-stage-head">
        <div className="curriculum-stage-copy">
          <span className="curriculum-stage-kicker">
            {t("progress.curriculumStageCounter", {
              current: curriculum.stage_position,
              total: curriculum.total_stages,
            })}
          </span>
          <h3>{curriculum.current_stage_title}</h3>
          <p>{curriculum.current_stage_description}</p>
        </div>
        <div className="curriculum-stage-meta">
          <span className="label">{t("progress.curriculumModule")}</span>
          <strong>{curriculum.current_module_title}</strong>
        </div>
      </div>
      <div className="curriculum-stage-body">
        <div className="plan-item">
          <span className="label">{t("progress.curriculumRationale")}</span>
          <p>{curriculum.rationale}</p>
        </div>
        <div className="curriculum-stage-metrics">
          <article className="curriculum-metric-card">
            <strong>{t(`progress.mastery.${curriculum.mastery_status}`)}</strong>
            <span>{t("progress.masteryStatus")}</span>
          </article>
          <article className="curriculum-metric-card">
            <strong>
              {formatReviewSchedule(
                t,
                curriculum.review_status,
                curriculum.next_review_in_sessions
              )}
            </strong>
            <span>{t("progress.reviewSchedule")}</span>
          </article>
        </div>
        <div className="plan-item">
          <span className="label">{t("progress.attentionReason")}</span>
          <p>{curriculum.attention_reason}</p>
        </div>
        <div className="plan-item">
          <span className="label">{t("progress.curriculumStageTargets")}</span>
          <div className="plan-focus-skills">
            {curriculum.target_subskills.map((skill) => (
              <span className="skill-tag" key={skill}>
                {subskillLabel(skill)}
              </span>
            ))}
          </div>
        </div>
        <div className="curriculum-stage-metrics">
          <article className="curriculum-metric-card">
            <strong>{curriculum.metrics.completed_sessions}</strong>
            <span>{t("progress.curriculumCompletedSessions")}</span>
          </article>
          <article className="curriculum-metric-card">
            <strong>
              {curriculum.metrics.required_scenarios_completed}/
              {curriculum.metrics.required_scenarios_total}
            </strong>
            <span>{t("progress.curriculumRequiredScenarios")}</span>
          </article>
          <article className="curriculum-metric-card">
            <strong>{curriculum.metrics.average_stage_score.toFixed(1)}</strong>
            <span>{t("progress.curriculumAverageScore")}</span>
          </article>
          <article className="curriculum-metric-card">
            <strong>{curriculum.metrics.target_subskill_average.toFixed(2)}/5</strong>
            <span>{t("progress.curriculumTargetAverage")}</span>
          </article>
        </div>
        <div className="plan-item">
          <span className="label">{t("progress.curriculumStageScenarios")}</span>
          <div className="curriculum-scenario-list">
            {curriculum.current_stage_scenarios.map((scenario) => (
              <article className="curriculum-scenario-row" key={scenario.scenario_id}>
                <div className="curriculum-scenario-copy">
                  <strong>{scenario.title}</strong>
                  <span>
                    {scenario.required
                      ? t("progress.curriculumRequired")
                      : t("progress.curriculumOptional")}
                  </span>
                </div>
                <div className="curriculum-scenario-stats">
                  <span>
                    {t("progress.curriculumAttemptCount")}
                    {scenario.attempt_count}
                  </span>
                  <span>
                    {t("progress.curriculumRemainingRepeats")}
                    {scenario.remaining_repetitions}
                  </span>
                </div>
              </article>
            ))}
          </div>
        </div>
        {curriculum.next_stage_title ? (
          <div className="plan-item">
            <span className="label">{t("progress.curriculumNextStage")}</span>
            <p>{curriculum.next_stage_title}</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function MasteryReviewPanel({ rows }: { rows: SkillRow[] }) {
  const { t } = useTranslation();

  const statusCounts = useMemo(() => {
    const counts = {
      needs_practice: 0,
      improving: 0,
      stable: 0,
      mastered: 0,
    };
    rows.forEach(({ payload }) => {
      const status = payload?.mastery_status;
      if (status && status in counts) {
        counts[status as keyof typeof counts] += 1;
      }
    });
    return counts;
  }, [rows]);

  const actionableRows = useMemo(() => {
    return rows
      .filter((item) => item.payload)
      .sort((left, right) => {
        const leftPayload = left.payload;
        const rightPayload = right.payload;
        const leftPriority = REVIEW_PRIORITY[leftPayload?.review_status ?? "maintain"] ?? 9;
        const rightPriority = REVIEW_PRIORITY[rightPayload?.review_status ?? "maintain"] ?? 9;
        if (leftPriority !== rightPriority) {
          return leftPriority - rightPriority;
        }
        const leftNext = leftPayload?.next_review_in_sessions ?? Number.MAX_SAFE_INTEGER;
        const rightNext = rightPayload?.next_review_in_sessions ?? Number.MAX_SAFE_INTEGER;
        if (leftNext !== rightNext) {
          return leftNext - rightNext;
        }
        const leftAverage = leftPayload?.rolling_average ?? 0;
        const rightAverage = rightPayload?.rolling_average ?? 0;
        return leftAverage - rightAverage;
      })
      .slice(0, 4);
  }, [rows]);

  return (
    <section className="panel surface-card mastery-review-panel">
      <div className="section-header">
        <div className="section-title">
          <AppIcon className="icon-md icon-brand" name="trend" />
          <span>{t("progress.masteryReview")}</span>
        </div>
      </div>
      <div className="mastery-summary-grid">
        {(["needs_practice", "improving", "stable", "mastered"] as const).map((status) => (
          <article className="mastery-summary-card" key={status}>
            <strong>{statusCounts[status]}</strong>
            <span>{t(`progress.mastery.${status}`)}</span>
          </article>
        ))}
      </div>
      <div className="review-schedule-list">
        {actionableRows.map(({ skillId, payload }) => (
          <article className="review-schedule-row" key={skillId}>
            <div className="review-schedule-copy">
              <div className="review-schedule-head">
                <strong>{subskillLabel(skillId)}</strong>
                <div className="badge-row">
                  <span className={`status-badge compact ${masteryBadgeTone(payload?.mastery_status)}`}>
                    {t(`progress.mastery.${payload?.mastery_status ?? "needs_practice"}`)}
                  </span>
                  <span className={`status-badge compact ${reviewBadgeTone(payload?.review_status)}`}>
                    {t(`progress.reviewStatus.${payload?.review_status ?? "maintain"}`)}
                  </span>
                </div>
              </div>
              <p>{payload?.status_reason ?? t("progress.noStatusReason")}</p>
            </div>
            <span className="review-schedule-meta">
              {formatReviewSchedule(t, payload?.review_status, payload?.next_review_in_sessions)}
            </span>
          </article>
        ))}
      </div>
    </section>
  );
}

function worldNodeTone(status: string): "success" | "warn" | "brand" {
  if (status === "completed") return "success";
  if (status === "active") return "warn";
  return "brand";
}

function SkillWorldMapPanel({ world }: { world?: SkillWorld | null }) {
  const { t } = useTranslation();
  if (!world) return null;

  const activeNode = world.nodes.find((node) => node.node_id === world.active_node_id);
  const earnedAchievements = world.achievements.slice(0, 4);

  return (
    <section className="panel surface-card skill-world-panel">
      <div className="section-header">
        <div className="section-title">
          <AppIcon className="icon-md icon-brand" name="globe" />
          <span>{t("progress.skillWorld")}</span>
        </div>
        <span className="status-badge brand">
          {world.summary.map_progress_percent}%
        </span>
      </div>
      <div className="skill-world-layout">
        <div className="skill-world-main">
          <div className="skill-world-summary">
            <article>
              <strong>
                {world.summary.completed_stage_count}/{world.summary.total_stage_count}
              </strong>
              <span>{t("progress.worldStages")}</span>
            </article>
            <article>
              <strong>
                {world.summary.mastered_subskill_count}/{world.summary.total_subskill_count}
              </strong>
              <span>{t("progress.worldMasteredSkills")}</span>
            </article>
            <article>
              <strong>{world.summary.earned_achievement_count}</strong>
              <span>{t("progress.worldAchievements")}</span>
            </article>
          </div>
          <div className="skill-world-track" aria-label={String(t("progress.skillWorld"))}>
            {world.nodes.map((node) => (
              <article
                className={`world-node ${node.status}${node.node_id === world.active_node_id ? " is-active" : ""}`}
                key={node.node_id}
              >
                <div className="world-node-head">
                  <span className={`status-badge compact ${worldNodeTone(node.status)}`}>
                    {t(`progress.worldStatus.${node.status}`)}
                  </span>
                  <span className="world-node-position">{node.position}</span>
                </div>
                <h3>{node.title}</h3>
                <p>{node.rationale}</p>
                <div className="world-node-progress">
                  <span style={{ width: `${node.progress_percent}%` }} />
                </div>
                <div className="world-node-meta">
                  <span>
                    {node.required_scenarios_completed}/{node.required_scenarios_total}
                    {t("progress.worldRequiredShort")}
                  </span>
                  <span>
                    {node.completed_scenario_count}/{node.scenario_count}
                    {t("progress.worldScenarioShort")}
                  </span>
                </div>
                <div className="plan-focus-skills compact">
                  {node.target_subskills.slice(0, 3).map((skill) => (
                    <span className="skill-tag" key={`${node.node_id}-${skill}`}>
                      {subskillLabel(skill)}
                    </span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </div>
        <aside className="skill-world-side">
          <div className="plan-item">
            <span className="label">{t("progress.worldCurrentStage")}</span>
            <p>{activeNode?.title ?? world.summary.current_stage_title}</p>
          </div>
          <div className="world-achievement-list">
            <span className="label">{t("progress.worldEarnedAchievements")}</span>
            {earnedAchievements.length > 0 ? (
              earnedAchievements.map((achievement) => (
                <article className="world-achievement-row" key={achievement.achievement_id}>
                  <AppIcon className="icon-sm icon-brand" name="shield" />
                  <div>
                    <strong>{achievement.title}</strong>
                    <p>{achievement.description}</p>
                  </div>
                </article>
              ))
            ) : (
              <div className="placeholder-inline">{t("progress.worldNoAchievements")}</div>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}

export function ProgressFlow({
  initialLearnerId,
  orgId = null,
  viewerRole = null,
}: ProgressFlowProps) {
  const router = useRouter();
  const [isRoutePending, startRouteTransition] = useTransition();
  const { t, i18n } = useTranslation();
  const isSupervisorView = viewerRole === "supervisor";

  const [learnerId, _setLearnerId] = useState(initialLearnerId);
  const [snapshot, setSnapshot] = useState<ProgressSnapshotResponse | null>(null);
  const [crossSkills, setCrossSkills] = useState<CrossSkillDashboardEntry[]>([]);
  const [skillFilter, setSkillFilter] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const [startError, setStartError] = useState<StartSessionErrorDetails | null>(null);
  const [_loading, setLoading] = useState(false);
  const [startingScenarioId, setStartingScenarioId] = useState<string | null>(null);
  const [installingSkill, setInstallingSkill] = useState(false);

  const buildContextHref = (
    pathname: string,
    extraParams: Record<string, string | null | undefined> = {}
  ): string => {
    const searchParams = new URLSearchParams();
    if (orgId) {
      searchParams.set("org", orgId);
    }
    if (viewerRole) {
      searchParams.set("viewer", viewerRole);
    }
    Object.entries(extraParams).forEach(([key, value]) => {
      if (typeof value === "string" && value.trim()) {
        searchParams.set(key, value);
      }
    });
    const query = searchParams.toString();
    return query ? `${pathname}?${query}` : pathname;
  };

  useEffect(() => {
    const loadSnapshot = async (targetLearnerId: string) => {
      if (!targetLearnerId.trim()) {
        return;
      }
      setLoading(true);
      setError(null);
      setStartError(null);
      try {
        const data = await readOptionalProgressSnapshot(targetLearnerId, {
          orgId,
          viewerRole,
        });
        setSnapshot(data);
      } catch (loadError) {
        setSnapshot(null);
        setError(loadError instanceof Error ? loadError.message : "Unknown progress loading error");
      } finally {
        setLoading(false);
      }
      try {
        const dash = await fetchCrossSkillDashboard(orgId || "local", targetLearnerId);
        setCrossSkills(dash.skills);
      } catch {
        // Cross-skill data is non-critical
        setCrossSkills([]);
      }
    };

    void loadSnapshot(initialLearnerId);
  }, [initialLearnerId, orgId, viewerRole]);

  const skillRows = useMemo(() => {
    const source = snapshot?.subskills ?? {};
    return DEFAULT_SUBSKILL_ORDER.map((skillId) => ({
      skillId,
      payload: source[skillId] ?? null,
    }));
  }, [snapshot]);

  const filteredRecentHistory = useMemo(() => {
    const history = snapshot?.recent_history ?? [];
    if (skillFilter === "all") return history;
    return history.filter((item) => item.skill_id === skillFilter);
  }, [snapshot, skillFilter]);

  const trendScores = useMemo(() => {
    return filteredRecentHistory.slice(-6).map((item) => item.overall_score);
  }, [filteredRecentHistory]);

  const practicePath = useMemo<Array<PracticePathEntry | ScenarioRecommendation>>(
    () => snapshot?.practice_path ?? snapshot?.latest_recommendations ?? [],
    [snapshot]
  );

  const lastScore = snapshot?.coach_memory.last_session?.overall_score ?? (trendScores.length > 0 ? trendScores[trendScores.length - 1] : null);
  const prevScore = trendScores.length >= 2 ? trendScores[trendScores.length - 2] : null;

  const startScenario = async (scenarioId: string) => {
    const targetLearnerId = snapshot?.learner_id ?? learnerId.trim();
    if (!targetLearnerId) {
      return;
    }
    setStartingScenarioId(scenarioId);
    setError(null);
    setStartError(null);
    try {
      const data = await startRuntimeSession(targetLearnerId, scenarioId, {
        orgId,
        viewerRole,
      }, i18n.language);
      startRouteTransition(() => {
        router.push(`/sessions/${data.session_id}?scenario=${scenarioId}`);
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
    const targetOrgId = startError.orgId || orgId || "local";
    setInstallingSkill(true);
    setError(null);
    try {
      await installOrgSkill(targetOrgId, startError.skillId);
      setStartError(null);
      setError(t("marketplace.installSuccess"));
    } catch (installError) {
      const message = installError instanceof Error ? installError.message : t("marketplace.installFailed");
      setError(`${t("marketplace.installFailed")}: ${message}`);
    } finally {
      setInstallingSkill(false);
    }
  }, [orgId, startError, t]);

  const difficultyLabel = (difficulty: string | null | undefined): string => {
    switch (difficulty) {
      case "easy":
        return String(t("scenarios.easy"));
      case "medium":
        return String(t("scenarios.medium"));
      case "hard":
        return String(t("scenarios.hard"));
      default:
        return difficulty ?? "-";
    }
  };

  /* Mock key evidence turns for display */
  const mockKeyTurns = [
    {
      turn: 3,
      phase: t("progress.mockTurn1"),
      status: "success" as const,
      excerpt: t("progress.mockExcerpt1"),
      label: t("progress.mockReason1"),
      labelType: "brand" as const,
    },
    {
      turn: 8,
      phase: t("progress.mockTurn2"),
      status: "warn" as const,
      excerpt: t("progress.mockExcerpt2"),
      label: t("progress.mockReason2"),
      labelType: "danger" as const,
    },
    {
      turn: 10,
      phase: t("progress.mockTurn3"),
      status: "success" as const,
      excerpt: t("progress.mockExcerpt3"),
      label: t("progress.mockReason3"),
      labelType: "brand" as const,
    },
  ];

  return (
    <section className="dashboard-page">
      <h1 className="progress-page-title">{t("progress.pageTitle")}</h1>

      {startError ? (
        <StartSessionErrorBanner
          canInstall={canManageSkillInstall(viewerRole)}
          error={startError}
          installBusy={installingSkill}
          onInstall={() => {
            void installMissingSkill();
          }}
        />
      ) : error ? <div className="error-banner">{error}</div> : null}

      {snapshot ? (
        <>
          {/* ─── Hero card ─── */}
          <section className="progress-hero-card surface-card">
            <div className="progress-hero-main">
              <div className="progress-hero-icon">
                <AppIcon className="icon-xl icon-brand" name="clipboard" />
              </div>
              <div className="progress-hero-copy">
                <h2>{snapshot.coach_memory.last_session?.scenario_title ?? t("progress.defaultScenarioTitle")}</h2>
                <div className="progress-hero-meta">
                  <span>
                    <AppIcon className="icon-sm" name="clock" />
                    {t("progress.completionTime")}{formatTimestamp(snapshot.coach_memory.last_session?.timestamp ?? snapshot.updated_at)}
                  </span>
                  <span>
                    <AppIcon className="icon-sm" name="clock" />
                    {t("progress.duration")}
                  </span>
                </div>
              </div>
            </div>

            <div className="progress-hero-score">
              <span className="progress-hero-score-label">{t("progress.totalScore")}</span>
              <div className="progress-hero-score-value">
                <strong>{lastScore ?? 76}</strong>
                <span>/ 100</span>
              </div>
            </div>

            <div className="progress-hero-weak">
              <span className="progress-hero-weak-label">{t("progress.mainWeakness")}</span>
              <div className="tag-list">
                {(snapshot.coach_memory.active_focus_subskills ?? ["need_discovery", "objection_handling"]).slice(0, 2).map((item) => (
                  <span className="warning-tag" key={item}>
                    {subskillLabel(item)}
                  </span>
                ))}
              </div>
            </div>

            <div className="progress-hero-next">
              <span className="progress-hero-next-label">{t("progress.nextSteps")}</span>
              {isSupervisorView ? (
                <span className="progress-hero-next-action">
                  {snapshot.coach_memory.next_actions?.[0] ?? t("progress.defaultNextAction")}
                </span>
              ) : (
                <Link className="progress-hero-next-action" href="/scenarios">
                  {snapshot.coach_memory.next_actions?.[0] ?? t("progress.defaultNextAction")}
                  <AppIcon className="icon-sm" name="arrow-right" />
                </Link>
              )}
            </div>

            {isSupervisorView ? null : (
              <button
                className="primary-button progress-hero-btn"
                disabled={!practicePath[0] || startingScenarioId !== null || isRoutePending}
                onClick={() =>
                  practicePath[0] &&
                  void startScenario(practicePath[0].scenario_id)
                }
                type="button"
              >
                <AppIcon className="icon-sm" name="play" />
                <span>{startingScenarioId || isRoutePending ? t("progress.starting") : t("progress.trainAgain")}</span>
              </button>
            )}
          </section>

          <SkillWorldMapPanel world={snapshot.skill_world} />

          {crossSkills.length > 0 ? (
            <section className="panel surface-card" style={{ padding: "0.75rem 1rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <span className="records-filter-label" style={{ fontSize: "0.85rem", whiteSpace: "nowrap" }}>{t("progress.skillFilter")}</span>
              <div className="filter-select-wrap" style={{ maxWidth: "220px" }}>
                <select
                  className="filter-select"
                  onChange={(event) => setSkillFilter(event.target.value)}
                  value={skillFilter}
                >
                  <option value="all">{t("records.allSkills")}</option>
                  {crossSkills.map((skill) => (
                    <option key={skill.skill_id} value={skill.skill_id}>
                      {skill.skill_name}
                    </option>
                  ))}
                </select>
                <AppIcon className="icon-sm filter-select-arrow" name="chevron-down" />
              </div>
            </section>
          ) : null}

          {/* ─── Two-column body ─── */}
          <div className="dashboard-columns">
            {/* Left column */}
            <div className="dashboard-column">
              <ActiveTeachingPlanPanel plan={snapshot.coach_memory.teaching_plan} />
              <CurriculumStagePanel curriculum={snapshot.curriculum} />
              <MasteryReviewPanel rows={skillRows} />

              {/* 七个子技能评分 */}
              <section className="panel surface-card">
                <div className="section-header">
                  <div className="section-title">
                    <AppIcon className="icon-md icon-brand" name="chart" />
                    <span>{t("progress.subskillScores")}</span>
                  </div>
                  <Link
                    className="section-link"
                    href={buildContextHref("/progress", { learner: snapshot.learner_id })}
                  >
                    {t("progress.viewDetails")} <AppIcon className="icon-sm" name="arrow-right" />
                  </Link>
                </div>
                <div className="skill-list">
                  {skillRows.map(({ skillId, payload }, index) => {
                    const percent = scorePercent(payload?.rolling_average ?? payload?.last_score ?? 0);
                    return (
                      <article className="skill-row" key={skillId}>
                        <span className="skill-index">{index + 1}</span>
                        <div className="skill-main">
                          <div className="skill-heading">
                            <strong>{subskillLabel(skillId)}</strong>
                            <span>{percent}%</span>
                          </div>
                          <div className={`progress-bar${percent < 55 ? " warn" : ""}`}>
                            <span style={{ width: `${percent}%` }} />
                          </div>
                        </div>
                        <div className="skill-side">
                          <span>{t("progress.level")} {payload?.level ?? "-"}</span>
                          {payload?.mastery_status ? (
                            <span className={`status-badge compact ${masteryBadgeTone(payload.mastery_status)}`}>
                              {t(`progress.mastery.${payload.mastery_status}`)}
                            </span>
                          ) : null}
                          {payload?.review_status ? (
                            <small className="skill-side-note">
                              {formatReviewSchedule(
                                t,
                                payload.review_status,
                                payload.next_review_in_sessions
                              )}
                            </small>
                          ) : null}
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>

              {/* 复盘要点 */}
              <section className="panel surface-card">
                <div className="section-header">
                  <div className="section-title">
                    <AppIcon className="icon-md icon-brand" name="star" />
                    <span>{t("progress.reviewHighlights")}</span>
                  </div>
                </div>
                <div className="review-notes-grid">
                  <article className="review-note-card good">
                    <div className="review-note-title">
                      <AppIcon className="icon-md" name="shield" />
                      <span>{t("progress.wentWell")}</span>
                    </div>
                    <ul className="bullet-list">
                      <li>{t("progress.mockGood1")}</li>
                      <li>{t("progress.mockGood2")}</li>
                      <li>{t("progress.mockGood3")}</li>
                    </ul>
                  </article>
                  <article className="review-note-card improve">
                    <div className="review-note-title">
                      <AppIcon className="icon-md" name="spark" />
                      <span>{t("progress.improve")}</span>
                    </div>
                    <ul className="bullet-list">
                      <li>{t("progress.mockImprove1")}</li>
                      <li>{t("progress.mockImprove2")}</li>
                      <li>{t("progress.mockImprove3")}</li>
                    </ul>
                  </article>
                  <article className="review-note-card compliance">
                    <div className="review-note-title">
                      <AppIcon className="icon-md" name="flag" />
                      <span>{t("progress.compliance")}</span>
                    </div>
                    <ul className="bullet-list">
                      <li>{t("progress.mockComp1")}</li>
                      <li>{t("progress.mockComp2")}</li>
                      <li>{t("progress.mockComp3")}</li>
                    </ul>
                  </article>
                </div>
              </section>
            </div>

            {/* Right column */}
            <div className="dashboard-column">
              {/* 关键证据片段（回合） */}
              <section className="panel surface-card">
                <div className="section-header">
                  <div className="section-title">
                    <AppIcon className="icon-md icon-brand" name="star" />
                    <span>{t("progress.keyTurns")}</span>
                  </div>
                  {isSupervisorView ? null : (
                    <Link className="section-link" href="/records">
                      {t("progress.viewFullChat")} <AppIcon className="icon-sm" name="arrow-right" />
                    </Link>
                  )}
                </div>
                <div className="evidence-turn-stack">
                  {mockKeyTurns.map((turn) => (
                    <article className="evidence-turn-row" key={turn.turn}>
                      <div className="evidence-turn-indicator">
                        <span className={`evidence-turn-dot ${turn.status}`} />
                      </div>
                      <div className="evidence-turn-body">
                        <div className="evidence-turn-head">
                          <span className="evidence-turn-tag">Turn {turn.turn}</span>
                          <strong>{turn.phase}</strong>
                        </div>
                        <p>{turn.excerpt}</p>
                      </div>
                      <div className="evidence-turn-label-col">
                        <span className="evidence-turn-label-title">{t("progress.tagReason")}</span>
                        <strong className={`evidence-turn-reason ${turn.labelType}`}>{turn.label}</strong>
                      </div>
                      <button className="icon-arrow-button" type="button">
                        <AppIcon className="icon-sm" name="arrow-right" />
                      </button>
                    </article>
                  ))}
                </div>
              </section>

              {/* Performance Analytics (Trend & Plateau Risk) */}
              {snapshot.performance_analytics && (
                <section className="panel surface-card">
                  <div className="section-header">
                    <div className="section-title">
                      <AppIcon className="icon-md icon-brand" name="trend" />
                      <span>{t("progress.performanceAnalytics")}</span>
                    </div>
                  </div>
                  <div className="analytics-layout">
                    <div className="analytics-main">
                      <div className="analytics-metric">
                        <span className="analytics-label">{t("progress.analyticsOverallTrend")}</span>
                        <strong className={`analytics-value trend-${snapshot.performance_analytics.overall_trend}`}>
                          {t(`progress.trend.${snapshot.performance_analytics.overall_trend}`)}
                        </strong>
                      </div>
                      <div className="analytics-metric">
                        <span className="analytics-label">{t("progress.analyticsRollingAverage")}</span>
                        <strong className="analytics-value">{snapshot.performance_analytics.rolling_average}</strong>
                      </div>
                    </div>
                    {snapshot.performance_analytics.plateau_risk && (
                      <div className="analytics-alert plateau-warning">
                        <AppIcon className="icon-sm" name="flag" />
                        <span>{t("progress.plateauRiskDetected")}</span>
                      </div>
                    )}
                  </div>
                </section>
              )}

              {/* 经验值与成长趋势 */}
              <section className="panel surface-card">
                <div className="section-header">
                  <div className="section-title">
                    <AppIcon className="icon-md icon-brand" name="trend" />
                    <span>{t("progress.expTrends")}</span>
                  </div>
                  <div className="section-select">
                    <select defaultValue="this">
                      <option value="this">{t("progress.thisSession")}</option>
                      <option value="week">{t("progress.thisWeek")}</option>
                    </select>
                    <AppIcon className="icon-sm" name="chevron-down" />
                  </div>
                </div>
                <div className="exp-trend-layout">
                  <div className="exp-table-panel">
                    <div className="exp-table-head">
                      <strong>{t("progress.expGrowth")}</strong>
                    </div>
                    <div className="exp-table">
                      <div className="exp-table-header-row">
                        <span>{t("progress.subskill")}</span>
                        <span>{t("progress.expGrowth")}</span>
                        <span>{t("progress.level")}</span>
                      </div>
                      {skillRows.map(({ skillId, payload }) => {
                        const isWeak = skillId === "need_discovery" || skillId === "objection_handling";
                        return (
                          <div className={`exp-table-row${isWeak ? " is-weak" : ""}`} key={skillId}>
                            <span className={isWeak ? "weak-text" : ""}>{subskillLabel(skillId)}</span>
                            <span>+{payload?.exp ?? Math.floor(Math.random() * 28 + 8)} EXP</span>
                            <span>Lv. {payload?.level ?? "-"}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  <div className="exp-chart-panel">
                    <strong className="exp-chart-title">{t("progress.overallTrend")}</strong>
                    <div className="trend-chart-card compact">
                      <svg className="trend-chart" viewBox="0 0 260 140" preserveAspectRatio="none">
                        <polyline points={sparklinePoints(trendScores.length ? trendScores : [52, 63, 71, 66, 72, 76], 240, 100)} />
                      </svg>
                      <div className="exp-chart-axis">
                        <span>{t("progress.lastSession")}</span>
                        <span>{t("progress.thisSession")}</span>
                      </div>
                    </div>
                    <div className="exp-score-change">
                      <span>{t("progress.scoreChange")}</span>
                  <strong>
                        {prevScore ?? 56} → {lastScore ?? 76}
                        <span className="score-delta positive">（+{(lastScore ?? 76) - (prevScore ?? 56)}）</span>
                      </strong>
                    </div>
                  </div>
                </div>
              </section>
            </div>
          </div>

          {/* ─── 下一轮推荐场景 ─── */}
          <section className="panel surface-card">
            <div className="section-header">
              <div className="section-title">
                <AppIcon className="icon-md icon-brand" name="rocket" />
                <span>{t("progress.practicePath")}</span>
              </div>
            </div>
            <div className="recommend-bottom-grid path-v2">
              {practicePath.slice(0, 3).map((item, idx) => {
                const stepIndex = "step_index" in item ? item.step_index : idx + 1;
                return (
                  <article className="recommend-path-card" key={item.scenario_id}>
                    <div className="path-step-badge">{stepIndex}</div>
                    <ThumbnailArtwork
                      className="recommend-path-thumb"
                      variant={scenarioArtVariant(item.scenario_id, item.target_subskills)}
                    />
                    <div className="recommend-path-copy">
                      <h3>{item.title}</h3>
                      <div className="path-meta">
                        {item.target_subskills.length > 0 ? (
                          <span className="path-evidence">
                            {t("progress.practiceFocus")}
                            {item.target_subskills.map((skill) => subskillLabel(skill)).join(", ")}
                          </span>
                        ) : null}
                        <span className="path-evidence">
                          {t("progress.expectedDifficulty")}
                          {difficultyLabel(item.expected_difficulty ?? item.difficulty)}
                        </span>
                      </div>
                      <div className="path-meta">
                        <span className="path-reason">
                          <AppIcon className="icon-xs" name="info" />
                          {item.reason}
                        </span>
                        {item.evidence_source && (
                          <span className="path-evidence">
                            {t("progress.evidenceSource")}{item.evidence_source}
                          </span>
                        )}
                      </div>
                      {item.stop_condition && (
                        <div className="path-stop">
                          <AppIcon className="icon-xs" name="spark" />
                          <span>{t("progress.stopCondition")}{item.stop_condition}</span>
                        </div>
                      )}
                      <div className="path-meta">
                        {item.urgency ? (
                          <span className={`path-evidence urgency-${item.urgency}`}>
                            {t("progress.urgencyReason")}{t(`progress.urgency.${item.urgency}`)}
                            {item.urgency_reason ? ` — ${item.urgency_reason}` : ""}
                          </span>
                        ) : null}
                        {item.reason_category ? (
                          <span className="path-evidence">
                            {t("progress.reasonCategory")}{t(`progress.driver.${item.reason_category}`)}
                          </span>
                        ) : null}
                        {item.suggested_repetition_count ? (
                          <span className="path-evidence">
                            {t("progress.repetitionCount")}{item.suggested_repetition_count}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    {isSupervisorView ? null : (
                      <button
                        className="ghost-button"
                        disabled={startingScenarioId === item.scenario_id}
                        onClick={() => void startScenario(item.scenario_id)}
                        type="button"
                      >
                        <AppIcon className="icon-sm" name="play" />
                        <span>{t("progress.startNow")}</span>
                      </button>
                    )}
                  </article>
                );
              })}
              {practicePath.length === 0 ? (
                <div className="placeholder-inline">{t("progress.noRecommendYet")}</div>
              ) : null}
            </div>
          </section>
        </>
      ) : (
        <div className="placeholder-block surface-card">
          <strong>{t("progress.noSnapshot")}</strong>
          <p>{t("progress.enterId")}</p>
          <div className="placeholder-actions">
            <Link
              className="primary-button"
              href={isSupervisorView ? buildContextHref("/team") : "/scenarios"}
            >
              {isSupervisorView ? t("team.backToTeam") : t("progress.goTrain")}
            </Link>
          </div>
        </div>
      )}
    </section>
  );
}

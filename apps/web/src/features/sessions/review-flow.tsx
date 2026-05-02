"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";

import { AppIcon, ThumbnailArtwork } from "@/components/app-graphics";
import { StartSessionErrorBanner } from "@/components/start-session-error-banner";
import {
  difficultyStars,
  formatDuration,
  formatTimestamp,
  scenarioArtVariant,
  scorePercent,
  sparklinePoints,
  subskillLabel,
} from "@/lib/mr-ui";
import {
  buildRuntimeProxyPath,
  installOrgSkill,
  readOptionalProgressSnapshot,
  readRuntimeJson,
  startRuntimeSession,
  type RuntimeRequestContext,
  type ProgressSnapshotResponse,
  type ReviewEvidence,
  type ReviewResponse,
  type ReviewSubskillScore,
  type SessionEventEnvelope,
  type SessionEventsResponse,
  type TeachingPlan,
  type TeachingPlanAchievement,
  type TeachingPlanSnapshot,
} from "@/lib/runtime-api";
import {
  canManageSkillInstall,
  parseStartSessionError,
  type StartSessionErrorDetails,
} from "@/lib/start-session-error";

type ReviewFlowProps = {
  sessionId: string;
  orgId?: string | null;
  viewerRole?: string | null;
};

type ReviewPayload = ReviewResponse & { finished_at?: string };
type ReviewSubskillRow = [string, ReviewSubskillScore];

type ReviewEvidenceCard = {
  key: string;
  skillId: string;
  summary: string;
  excerpt: string | null;
  turnIndex: number | null;
};

const REVIEW_PREFIX = "mr_session_review:";

function reviewStorageKey(sessionId: string): string {
  return `${REVIEW_PREFIX}${sessionId}`;
}

function evidenceSummary(evidence: ReviewEvidence, t: (k: string) => string): string {
  if (typeof evidence === "string") {
    return evidence;
  }
  return evidence.summary ?? evidence.excerpt ?? t("review.evidence");
}

function evidenceExcerpt(evidence: ReviewEvidence): string | null {
  if (typeof evidence === "string") {
    return null;
  }
  return evidence.excerpt ?? null;
}

function evidenceTurnIndex(evidence: ReviewEvidence): number | null {
  if (typeof evidence === "string") {
    return null;
  }
  return typeof evidence.turn_index === "number" ? evidence.turn_index : null;
}

function eventTurnContent(event: SessionEventEnvelope) {
  return event.content ?? {};
}

function eventTurnIndex(event: SessionEventEnvelope): number | null {
  const value = eventTurnContent(event).turn_index;
  return typeof value === "number" ? value : null;
}

function eventDirectorEvents(event: SessionEventEnvelope): string[] {
  const value = eventTurnContent(event).director_events;
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function eventRecommendedAction(event: SessionEventEnvelope): string | null {
  const value = eventTurnContent(event).recommended_action;
  return typeof value === "string" && value.trim() ? value : null;
}

function keyMomentLabel(event: SessionEventEnvelope, t: (k: string) => string): string {
  const directorEvents = eventDirectorEvents(event);
  if (directorEvents.length > 0) {
    return directorEvents[0].replaceAll("_", " ");
  }
  return eventRecommendedAction(event)?.replaceAll("_", " ") ?? t("review.keyMoment");
}

function ContinuityAchievementPanel({
  achievement,
  teachingPlan,
  teachingPlanSnapshot,
}: {
  achievement?: TeachingPlanAchievement;
  teachingPlan?: TeachingPlan | null;
  teachingPlanSnapshot?: TeachingPlanSnapshot | null;
}) {
  const { t } = useTranslation();
  if (!achievement || achievement.status === "no_plan") return null;

  const status = achievement.status as string;
  const statusKey =
    status === "partially_achieved" ? "partiallyAchieved"
    : status === "not_achieved" ? "notAchieved"
    : status === "not_observable" ? "notObservable"
    : "achieved";
  const statusClass =
    status === "achieved" ? "success"
    : status === "partially_achieved" ? "warn"
    : status === "not_observable" ? "warn"
    : "error";

  return (
    <section className={`panel surface-card continuity-achievement-panel ${statusClass}`}>
      <div className="section-header">
        <div className="section-title">
          <AppIcon className="icon-md icon-brand" name="spark" />
          <span>{t("progress.planAchievement")}</span>
          <span className={`status-badge ${statusClass}`}>{t(`progress.${statusKey}`)}</span>
        </div>
      </div>
      <div className="achievement-content">
        <div className="achievement-main">
          <div className="achievement-stat">
             <strong>{achievement.achieved_count} / {achievement.total_count}</strong>
             <span>{t("progress.successCriterion")}: {teachingPlan?.success_criterion}</span>
          </div>
          {teachingPlan?.version ? (
            <div className="achievement-advice">
              <AppIcon className="icon-sm" name="target" />
              <p>
                <strong>{t("progress.planVersion")}:</strong> v{teachingPlan.version}
                {teachingPlanSnapshot?.frozen_at ? ` · ${t("progress.planFrozenAt")}${formatTimestamp(teachingPlanSnapshot.frozen_at)}` : ""}
              </p>
            </div>
          ) : null}
          {teachingPlan?.target_behavior && (
            <div className="achievement-advice">
               <AppIcon className="icon-sm" name="info" />
               <p><strong>{t("progress.targetBehavior")}:</strong> {teachingPlan.target_behavior}</p>
            </div>
          )}
          {Array.isArray(teachingPlan?.prior_evidence) && teachingPlan.prior_evidence.length > 0 ? (
            <div className="achievement-advice">
              <AppIcon className="icon-sm" name="clipboard" />
              <div>
                <p><strong>{t("progress.priorEvidence")}:</strong></p>
                <ul className="bullet-list">
                  {teachingPlan.prior_evidence.slice(0, 2).map((item, index: number) => (
                    <li key={`${item.summary ?? "evidence"}-${index}`}>
                      {item.summary}
                      {item.scenario_title ? ` · ${item.scenario_title}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function BenchmarkingPanel({ score }: { score: number }) {
  const { t } = useTranslation();
  
  // Mock peer data for current version
  const peerAvg = 64;
  const top10Avg = 88;
  
  return (
    <section className="panel surface-card benchmarking-panel">
      <div className="section-header">
        <div className="section-title">
          <AppIcon className="icon-md icon-brand" name="chart" />
          <span>{t("progress.peerBenchmarking")}</span>
        </div>
      </div>
      <div className="benchmarking-content">
        <div className="benchmarking-score-row">
          <div className="benchmarking-score-item your-score">
            <span className="label">{t("progress.yourScore")}</span>
            <span className="value">{score}</span>
          </div>
          <div className="benchmarking-score-item peer-avg">
            <span className="label">{t("progress.peerAverage")}</span>
            <span className="value">{peerAvg}</span>
          </div>
          <div className="benchmarking-score-item top-10">
            <span className="label">{t("progress.top10Percent")}</span>
            <span className="value">{top10Avg}</span>
          </div>
        </div>
        <div className="benchmarking-visual">
          <div className="benchmarking-bar-container">
            <div className="benchmarking-bar-bg" />
            <div className="benchmarking-marker peer-marker" style={{ left: `${peerAvg}%` }}>
               <div className="marker-dot" />
               <span className="marker-label">{t("progress.average")}</span>
            </div>
            <div className="benchmarking-marker your-marker" style={{ left: `${score}%` }}>
               <div className="marker-dot" />
               <span className="marker-label">{t("progress.you")}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function ReviewFlow({
  sessionId,
  orgId = null,
  viewerRole = null,
}: ReviewFlowProps) {
  const router = useRouter();
  const [isRoutePending, startRouteTransition] = useTransition();
  const { t, i18n } = useTranslation();
  const isSupervisorView = viewerRole === "supervisor";
  const runtimeContext = useMemo<RuntimeRequestContext>(
    () => ({ orgId, viewerRole }),
    [orgId, viewerRole]
  );

  const [payload, setPayload] = useState<ReviewPayload | null>(null);
  const [progress, setProgress] = useState<ProgressSnapshotResponse | null>(null);
  const [events, setEvents] = useState<SessionEventEnvelope[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [startError, setStartError] = useState<StartSessionErrorDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [startingScenarioId, setStartingScenarioId] = useState<string | null>(null);
  const [installingSkill, setInstallingSkill] = useState(false);

  const buildContextHref = (
    pathname: string,
    extraParams: Record<string, string | number | null | undefined> = {}
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
      if (typeof value === "number" && Number.isFinite(value)) {
        searchParams.set(key, String(value));
      }
    });
    const query = searchParams.toString();
    return query ? `${pathname}?${query}` : pathname;
  };

  useEffect(() => {
    let active = true;
    const loadReview = async () => {
      setLoading(true);
      setError(null);
      setStartError(null);
      try {
        const data = await readRuntimeJson<ReviewResponse>(
          buildRuntimeProxyPath(`/api/runtime/sessions/${sessionId}/review`, runtimeContext)
        );
        if (active) {
          setPayload(data);
        }
      } catch (loadError) {
        const cached = localStorage.getItem(reviewStorageKey(sessionId));
        if (cached && active) {
          try {
            setPayload(JSON.parse(cached) as ReviewPayload);
          } catch {
            localStorage.removeItem(reviewStorageKey(sessionId));
          }
        }
        if (active) {
          setError(loadError instanceof Error ? loadError.message : "Unknown review load error");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    void loadReview();
    return () => {
      active = false;
    };
  }, [runtimeContext, sessionId]);

  useEffect(() => {
    if (!payload?.learner_id) {
      return;
    }
    let active = true;
    const loadExtras = async () => {
      const [eventsResult, progressResult] = await Promise.allSettled([
        readRuntimeJson<SessionEventsResponse>(
          buildRuntimeProxyPath(`/api/runtime/sessions/${sessionId}/events`, runtimeContext)
        ),
        readOptionalProgressSnapshot(payload.learner_id, runtimeContext),
      ]);

      if (!active) {
        return;
      }

      if (eventsResult.status === "fulfilled") {
        setEvents(Array.isArray(eventsResult.value.events) ? eventsResult.value.events : []);
      } else {
        setEvents([]);
      }

      if (progressResult.status === "fulfilled") {
        setProgress(progressResult.value);
      } else {
        setProgress(null);
      }
    };
    void loadExtras();
    return () => {
      active = false;
    };
  }, [payload?.learner_id, runtimeContext, sessionId]);

  const subskillRows = useMemo(() => {
    return Object.entries(payload?.review.subskills ?? {}) as ReviewSubskillRow[];
  }, [payload]);

  const displayedSubskillRows = useMemo<ReviewSubskillRow[]>(() => {
    return subskillRows.length > 0 ? subskillRows : [["need_discovery", { score: 2.8, evidence: [] }]];
  }, [subskillRows]);

  const reviewEvidenceCards = useMemo<ReviewEvidenceCard[]>(() => {
    const reviewSubskills = payload?.review.subskills ?? {};
    const skillOrder =
      (payload?.review.priority_subskills?.length ? payload.review.priority_subskills : Object.keys(reviewSubskills)) ??
      [];
    const cards: ReviewEvidenceCard[] = [];
    const seen = new Set<string>();

    for (const skillId of skillOrder) {
      const subskill = reviewSubskills[skillId];
      if (!subskill) {
        continue;
      }
      for (const item of subskill.evidence ?? []) {
        const summary = evidenceSummary(item, t);
        if (!summary) {
          continue;
        }
        const turnIndex = evidenceTurnIndex(item);
        const excerpt = evidenceExcerpt(item);
        const key = `${skillId}:${turnIndex ?? "na"}:${summary}`;
        if (seen.has(key)) {
          continue;
        }
        seen.add(key);
        cards.push({
          key,
          skillId,
          summary,
          excerpt,
          turnIndex,
        });
        if (cards.length >= 3) {
          return cards;
        }
      }
    }

    return cards;
  }, [payload, t]);

  const keyMoments = useMemo(() => {
    return events
      .filter((event) => event.type === "turn_processed")
      .filter(
        (event) =>
          eventDirectorEvents(event).length > 0 ||
          Boolean(eventRecommendedAction(event))
      )
      .slice(-3);
  }, [events]);

  const trendScores = useMemo(() => {
    return (progress?.recent_history ?? []).slice(-6).map((item) => item.overall_score);
  }, [progress]);

  const startScenario = async (scenarioId: string) => {
    if (!payload?.learner_id) {
      return;
    }
    setStartingScenarioId(scenarioId);
    setError(null);
    setStartError(null);
    try {
      const data = await startRuntimeSession(
        payload.learner_id,
        scenarioId,
        runtimeContext,
        i18n.language
      );
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

  if (loading) {
    return (
      <section className="dashboard-page">
        <div className="placeholder-block surface-card">
          <strong>{t("review.loading")}</strong>
          <p>{t("review.syncing")}</p>
        </div>
      </section>
    );
  }

  if (!payload) {
    const isPermissionError = error && /403|forbidden|restricted|denied/i.test(error);
    return (
      <section className="dashboard-page">
        <div className="placeholder-block surface-card">
          <strong>{isPermissionError ? t("restricted.reviewDetail") : t("review.noReview")}</strong>
          <p>{isPermissionError ? t("restricted.contactAdmin") : t("review.finishFirst")}</p>
          <div className="placeholder-actions">
            <Link
              className="primary-button"
              href={
                isSupervisorView
                  ? buildContextHref("/team")
                  : buildContextHref(`/records/${sessionId}`)
              }
            >
              {t("review.backToRecords")}
            </Link>
            <Link className="ghost-button" href="/scenarios">
              {t("review.backToScenarios")}
            </Link>
          </div>
        </div>
      </section>
    );
  }

  const nextActions = payload.review.coaching_feedback?.next_actions ?? payload.coach_memory?.next_actions ?? [];
  const recommendations = (progress?.practice_path ?? progress?.latest_recommendations ?? []).slice(0, 2);
  const duration = formatDuration(payload.started_at, payload.updated_at);
  const displayTitle = payload.review.display_title ?? payload.scenario?.title ?? payload.scenario_id;
  const frozenTeachingPlan = payload.coach_continuity?.teaching_plan ?? payload.coach_memory?.teaching_plan;
  const frozenTeachingPlanSnapshot = payload.coach_continuity?.teaching_plan_snapshot;

  return (
    <section className="dashboard-page">
      <h1 className="review-page-title">{t("progress.pageTitle")}</h1>
      {startError ? (
        <StartSessionErrorBanner
          canInstall={canManageSkillInstall(viewerRole)}
          error={startError}
          installBusy={installingSkill}
          onInstall={() => {
            void installMissingSkill();
          }}
        />
      ) : error ? (
        <div className="error-banner">
          {/403|forbidden|restricted|denied/i.test(error)
            ? isSupervisorView
              ? t("restricted.reviewDetail")
              : t("restricted.summaryOnly")
            : error}
        </div>
      ) : null}

      <section className="review-hero-card surface-card">
        <div className="review-hero-main">
          <div className="review-hero-icon">
            <AppIcon className="icon-xl icon-brand" name="clipboard" />
          </div>
          <div className="review-hero-copy">
            <h2>{displayTitle}</h2>
            <div className="review-meta-row">
              <span>
                <AppIcon className="icon-sm" name="calendar" />
                {t("progress.completionTime")}{formatTimestamp(payload.updated_at)}
              </span>
              <span>
                <AppIcon className="icon-sm" name="clock" />
                {t("review.durationLabel")}{duration}
              </span>
            </div>
          </div>
        </div>

        <div className="review-hero-stats">
          <article>
            <span>{t("progress.totalScore")}</span>
            <strong>{payload.review.overall_score ?? "-"} / 100</strong>
          </article>
          <article>
            <span>{t("progress.mainWeakness")}</span>
            <div className="tag-list">
              {(payload.review.priority_subskills ?? []).slice(0, 2).map((item) => (
                <span className="warning-tag" key={item}>
                  {subskillLabel(item)}
                </span>
              ))}
            </div>
          </article>
          <article>
            <span>{t("progress.nextSteps")}</span>
            <strong>{nextActions[0] ?? t("review.defaultNext")}</strong>
          </article>
          {isSupervisorView ? null : (
            <button
              className="primary-button hero-button"
              disabled={startingScenarioId === payload.scenario_id || isRoutePending}
              onClick={() => void startScenario(payload.scenario_id)}
              type="button"
            >
              <AppIcon className="icon-sm" name="play" />
              <span>{startingScenarioId || isRoutePending ? t("progress.starting") : t("progress.trainAgain")}</span>
            </button>
          )}
        </div>
      </section>

      <div className="review-grid-two">
        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="chart" />
              <span>{t("progress.subskillScores")}</span>
            </div>
            <button className="section-link" type="button">
              {t("progress.viewDetails")}
            </button>
          </div>
          <div className="skill-list">
            {subskillRows.map(([skillId, item], index) => {
              const percent = scorePercent(item.score);
              const primaryEvidence = item.evidence[0];
              return (
                <article className="skill-row review-skill-row" key={skillId}>
                  <span className="skill-index">{index + 1}</span>
                  <div className="skill-main">
                    <div className="skill-heading">
                      <strong>{subskillLabel(skillId)}</strong>
                      <span>{percent}%</span>
                    </div>
                    <div className={`progress-bar${percent < 55 ? " warn" : ""}`}>
                      <span style={{ width: `${percent}%` }} />
                    </div>
                    {primaryEvidence ? (
                      <div className="review-skill-evidence">
                        <span>{evidenceSummary(primaryEvidence, t)}</span>
                        {evidenceTurnIndex(primaryEvidence) ? (
                          <small>{t("review.turnPrefix", { index: evidenceTurnIndex(primaryEvidence) })}</small>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                  <div className="skill-side">
                    <span>{t("progress.level")} {progress?.subskills?.[skillId]?.level ?? "-"}</span>
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="star" />
              <span>{t("progress.keyTurns")}</span>
            </div>
            {isSupervisorView ? null : (
              <Link className="section-link" href={buildContextHref(`/records/${sessionId}`)}>
                {t("progress.viewFullChat")}
              </Link>
            )}
          </div>
          <div className="timeline-list">
            {reviewEvidenceCards.length > 0 ? (
              reviewEvidenceCards.map((item, index) => (
                <article className="timeline-row" key={item.key}>
                  <div className={`timeline-dot${index === 0 ? " success" : " warn"}`} />
                  <div className="timeline-card">
                    <div className="timeline-turn-tag">
                      {item.turnIndex ? (
                        isSupervisorView ? (
                          <span>{t("review.turnPrefix", { index: item.turnIndex })}</span>
                        ) : (
                          <Link
                            href={buildContextHref(`/records/${sessionId}`, {
                              highlight_turn: item.turnIndex,
                            })}
                          >
                            {t("review.turnPrefix", { index: item.turnIndex })}
                            <AppIcon className="icon-xs ml-1" name="rocket" />
                          </Link>
                        )
                      ) : t("review.evidence")}
                    </div>
                    <div className="timeline-card-main">
                      <div>
                        <strong>{subskillLabel(item.skillId)}</strong>
                        <p>{item.summary}</p>
                        {item.excerpt ? <p className="timeline-evidence-quote">&ldquo;{item.excerpt}&rdquo;</p> : null}
                      </div>
                      <div className="timeline-side-note">
                        <span>{t("review.relatedSubskill")}</span>
                        <strong>{subskillLabel(item.skillId)}</strong>
                      </div>
                    </div>
                  </div>
                </article>
              ))
            ) : keyMoments.length === 0 ? (
              <div className="placeholder-inline">{t("review.noEvidence")}</div>
            ) : (
              keyMoments.map((event, index) => (
                <article className="timeline-row" key={`${eventTurnIndex(event) ?? index}-${index}`}>
                  <div className={`timeline-dot${index === 0 ? " success" : " warn"}`} />
                  <div className="timeline-card">
                    <div className="timeline-turn-tag">
                      {t("review.turnPrefix", { index: eventTurnIndex(event) ?? index + 1 })}
                    </div>
                    <div className="timeline-card-main">
                      <div>
                        <strong>{keyMomentLabel(event, t)}</strong>
                        <p>{payload.review.diagnosis?.primary?.[index]?.summary ?? t("review.markedAction")}</p>
                      </div>
                      <div className="timeline-side-note">
                        <span>{t("progress.tagReason")}</span>
                        <strong>
                          {(payload.review.diagnosis?.primary?.[index]?.recommendation_focus ?? [])
                            .map((item) => subskillLabel(item))
                            .join(", ") || t("review.keyAction")}
                        </strong>
                      </div>
                    </div>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>
      </div>

      <div className="review-grid-two">
        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="star" />
              <span>{t("progress.reviewHighlights")}</span>
            </div>
          </div>
          <div className="note-grid-three">
            <article className="note-card success">
              <div className="note-card-title">
                <AppIcon className="icon-md" name="shield" />
                <span>{t("progress.wentWell")}</span>
              </div>
              <ul className="bullet-list">
                {(payload.review.strengths ?? []).slice(0, 3).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </article>

            <article className="note-card warn">
              <div className="note-card-title">
                <AppIcon className="icon-md" name="spark" />
                <span>{t("progress.improve")}</span>
              </div>
              <ul className="bullet-list">
                {(payload.review.priority_subskills ?? []).slice(0, 3).map((item) => (
                  <li key={item}>{subskillLabel(item)}</li>
                ))}
                {nextActions.slice(0, 2).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </article>

            <article className="note-card compliance-panel">
              <div className="note-card-title">
                <AppIcon className="icon-md" name="shield" />
                <span>{t("progress.compliance")}</span>
                {payload.review.compliance_channel?.overall_status === "at_risk" && (
                  <span className="error-tag ml-auto">{t("review.atRisk")}</span>
                )}
              </div>
              <div className="compliance-list">
                {(payload.review.compliance_flags ?? []).map((item, index) => (
                  <div className="compliance-item" key={`${item.rule_id}-${index}`}>
                    <div className="compliance-item-header">
                      <span className={`severity-dot ${item.severity}`} />
                      <strong>{item.tag}</strong>
                    </div>
                    <p>{item.summary}</p>
                    {item.required_handling ? (
                      <div className={`compliance-handling ${item.severity === "positive" ? "success" : ""}`}>
                        <AppIcon className="icon-xs" name={item.severity === "positive" ? "shield" : "info"} />
                        <span>
                          {item.severity === "positive" ? t("review.correctHandling") : item.required_handling}
                          {item.severity === "positive" ? "" : `: ${item.required_handling}`}
                        </span>
                      </div>
                    ) : null}
                    {item.evidence?.[0] ? (
                      isSupervisorView ? (
                        <span className="compliance-evidence-link">
                          {t("review.turnPrefix", { index: evidenceTurnIndex(item.evidence[0]) })}
                        </span>
                      ) : (
                        <Link
                          className="compliance-evidence-link"
                          href={buildContextHref(`/records/${sessionId}`, {
                            highlight_turn: evidenceTurnIndex(item.evidence[0]),
                          })}
                        >
                          <AppIcon className="icon-xs mr-1" name="rocket" />
                          {t("review.turnPrefix", { index: evidenceTurnIndex(item.evidence[0]) })}
                        </Link>
                      )
                    ) : null}
                  </div>
                ))}
                {(payload.review.compliance_flags ?? []).length === 0 ? (
                  <p className="placeholder-text">{t("review.noCompliance")}</p>
                ) : null}
              </div>
            </article>
          </div>
        </section>

        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="trend" />
              <span>{t("progress.expTrends")}</span>
            </div>
            <span className="section-chip">{t("progress.thisSession")}</span>
          </div>
          <div className="growth-panel-layout">
            <div className="growth-mini-table">
              {displayedSubskillRows.map(([skillId, item]) => (
                <div className="growth-table-row" key={skillId}>
                  <span>{subskillLabel(skillId)}</span>
                  <strong>+{Math.max(8, Math.round(item.score * 6))} EXP</strong>
                  <small>Lv. {progress?.subskills?.[skillId]?.level ?? "-"}</small>
                </div>
              ))}
            </div>
            <div className="trend-chart-card compact">
              <svg className="trend-chart" viewBox="0 0 320 180">
                <polyline
                  points={sparklinePoints(
                    trendScores.length ? trendScores : [56, payload.review.overall_score ?? 76],
                    280,
                    120
                  )}
                />
              </svg>
              <div className="growth-total-change">
                <span>{t("progress.scoreChange")}</span>
                <strong>
                  {trendScores.length > 1
                    ? `${trendScores[0]} → ${trendScores.at(-1)}`
                    : `${Math.max((payload.review.overall_score ?? 76) - 12, 50)} → ${payload.review.overall_score ?? 76}`}
                </strong>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div className="review-grid-two">
        <ContinuityAchievementPanel 
          achievement={payload.review.continuity_channel?.teaching_plan_achievement} 
          teachingPlan={frozenTeachingPlan}
          teachingPlanSnapshot={frozenTeachingPlanSnapshot}
        />
        <BenchmarkingPanel score={payload.review.overall_score ?? 0} />
      </div>

      <section className="panel surface-card">
        <div className="section-header">
          <div className="section-title">
            <AppIcon className="icon-md icon-brand" name="rocket" />
            <span>{t("progress.nextRecommended")}</span>
          </div>
        </div>
        <div className="recommend-bottom-grid">
          {recommendations.length === 0 ? (
            <div className="placeholder-inline">{t("progress.noRecommendYet")}</div>
          ) : (
            recommendations.map((item) => (
              <article className="recommend-wide-card" key={item.scenario_id}>
                <ThumbnailArtwork
                  className="recommend-wide-thumb"
                  variant={scenarioArtVariant(item.scenario_id, item.target_subskills)}
                />
                <div className="recommend-wide-copy">
                  {item.recommendation_type === "compliance" ? (
                    <span className="remedial-tag">
                      <AppIcon className="icon-xs" name="alert" />
                      {t("review.complianceRemedial")}
                    </span>
                  ) : null}
                  <h3>{item.title}</h3>
                  <p>{t("progress.reason")}{item.reason}</p>
                  <small>
                    {t("review.difficulty")}{difficultyStars(item.difficulty)} · {t("records.focusTraining")}
                    {item.target_subskills.map((skill) => subskillLabel(skill)).join(", ")}
                  </small>
                </div>
                {isSupervisorView ? null : (
                  <button
                    className="ghost-button"
                    disabled={startingScenarioId === item.scenario_id}
                    onClick={() => void startScenario(item.scenario_id)}
                    type="button"
                  >
                    <AppIcon className="icon-sm" name="play" />
                    <span>{t("progress.startNext")}</span>
                  </button>
                )}
              </article>
            ))
          )}
        </div>
      </section>
    </section>
  );
}

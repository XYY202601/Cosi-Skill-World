"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";

import { AppIcon, ThumbnailArtwork } from "@/components/app-graphics";
import { StartSessionErrorBanner } from "@/components/start-session-error-banner";
import {
  DEFAULT_SUBSKILL_ORDER,
  difficultyStars,
  scenarioArtVariant,
  scorePercent,
  sparklinePoints,
  subskillLabel,
} from "@/lib/mr-ui";
import {
  readOptionalProgressSnapshot,
  readRuntimeJson,
  startRuntimeSession,
  installOrgSkill,
  fetchCrossSkillDashboard,
  type CrossSkillDashboardEntry,
  type ProgressSnapshotResponse,
  type ScenarioListResponse,
  type ScenarioSummary,
} from "@/lib/runtime-api";
import {
  canManageSkillInstall,
  parseStartSessionError,
  type StartSessionErrorDetails,
} from "@/lib/start-session-error";
import { useAuth } from "@/lib/auth-context";

const DEFAULT_LEARNER_ID = "learner_demo_001";

export function HomeDashboard() {
  const router = useRouter();
  const [isRoutePending, startRouteTransition] = useTransition();
  const { t, i18n } = useTranslation();
  const { user, authMode, isLoading: authLoading } = useAuth();
  const activeLearnerId = (authMode === "mock" || authMode === "oidc") && user ? user.learner_id : DEFAULT_LEARNER_ID;

  const [_loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startError, setStartError] = useState<StartSessionErrorDetails | null>(null);
  const [progress, setProgress] = useState<ProgressSnapshotResponse | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [startingScenarioId, setStartingScenarioId] = useState<string | null>(null);
  const [crossSkills, setCrossSkills] = useState<CrossSkillDashboardEntry[]>([]);
  const [installingSkill, setInstallingSkill] = useState(false);

  const loadDashboard = useCallback(async (learnerId: string) => {
    setLoading(true);
    setError(null);
    setStartError(null);
    const orgId = user?.org_id || "local";
    const [scenarioResult, progressResult, crossSkillResult] = await Promise.allSettled([
      readRuntimeJson<ScenarioListResponse>("/api/runtime/scenarios"),
      readOptionalProgressSnapshot(learnerId),
      fetchCrossSkillDashboard(orgId, learnerId),
    ]);

    if (scenarioResult.status === "fulfilled") {
      setScenarios(Array.isArray(scenarioResult.value.scenarios) ? scenarioResult.value.scenarios : []);
    } else {
      setScenarios([]);
    }
    if (progressResult.status === "fulfilled") {
      setProgress(progressResult.value);
    } else {
      setProgress(null);
    }
    if (crossSkillResult.status === "fulfilled") {
      setCrossSkills(crossSkillResult.value.skills);
    } else {
      setCrossSkills([]);
    }

    const failures = [scenarioResult, progressResult]
      .filter((item): item is PromiseRejectedResult => item.status === "rejected")
      .map((item) => item.reason)
      .filter((item): item is Error => item instanceof Error)
      .map((item) => item.message);
    setError(failures.length > 0 ? failures.join(" | ") : null);
    setLoading(false);
  }, [user]);

  useEffect(() => {
    if (authLoading) return;
    if ((authMode === "mock" || authMode === "oidc") && !user) return;
    void loadDashboard(activeLearnerId);
  }, [activeLearnerId, authLoading, authMode, loadDashboard, user]);

  const scenarioLookup = useMemo(() => {
    return new Map(scenarios.map((scenario) => [scenario.id, scenario]));
  }, [scenarios]);

  const skillRows = useMemo(() => {
    const source = progress?.subskills ?? {};
    return DEFAULT_SUBSKILL_ORDER.map((skillId) => ({
      skillId,
      payload: source[skillId] ?? null,
    }));
  }, [progress]);

  const recommendedRows = useMemo(() => {
    const practicePath = progress?.practice_path ?? progress?.latest_recommendations ?? [];
    const runtimeRows = practicePath.slice(0, 3).map((item) => ({
      ...item,
      scenario: scenarioLookup.get(item.scenario_id) ?? null,
    }));
    if (runtimeRows.length > 0) {
      return runtimeRows;
    }
    return scenarios.slice(0, 3).map((scenario) => ({
      scenario_id: scenario.id,
      title: scenario.title,
      difficulty: scenario.difficulty,
      target_subskills: scenario.focus_subskills,
      reason: t("home.focusTraining").replace("：", "") + ` ${scenario.focus_subskills.map((skill) => subskillLabel(skill)).join("、")}`,
      scenario,
    }));
  }, [progress, scenarioLookup, scenarios, t]);

  const featuredScenarioId = recommendedRows[0]?.scenario_id ?? scenarios[0]?.id ?? null;
  const latestHistory = progress?.recent_history.at(-1) ?? null;
  const trendScores = (progress?.recent_history ?? []).slice(-7).map((item) => item.overall_score);
  const averageScore =
    trendScores.length > 0
      ? Math.round(trendScores.reduce((sum, item) => sum + item, 0) / trendScores.length)
      : 0;

  const startTraining = async (scenarioId: string) => {
    setStartingScenarioId(scenarioId);
    setError(null);
    setStartError(null);
    try {
      const data = await startRuntimeSession(
        activeLearnerId,
        scenarioId,
        {
          orgId: user?.org_id ?? null,
          viewerRole: user?.role ?? null,
        },
        i18n.language
      );
      startRouteTransition(() => {
        router.push(`/sessions/${data.session_id}?scenario=${scenarioId}`);
      });
    } catch (startError) {
      const parsed = parseStartSessionError(startError, "Unknown start session error");
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
    const orgId = startError.orgId || user?.org_id || "local";
    setInstallingSkill(true);
    setError(null);
    try {
      await installOrgSkill(orgId, startError.skillId, {
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

  return (
    <section className="dashboard-page">
      <section className="hero-panel surface-card">
        <div className="hero-panel-main">
          <div className="hero-icon-tile">
            <AppIcon className="icon-hero" name="user" />
          </div>
          <div className="hero-panel-copy">
            <h1>{t("home.heroTitle")}</h1>
            <p>{t("home.heroSubtitle")}</p>
          </div>
        </div>
        <button
          className="primary-button hero-button"
          disabled={!featuredScenarioId || startingScenarioId !== null || isRoutePending || authLoading}
          onClick={() => featuredScenarioId && void startTraining(featuredScenarioId)}
        >
          <AppIcon className="icon-sm" name="play" />
          <span>{startingScenarioId || isRoutePending ? t("home.entering") : t("home.startTraining")}</span>
        </button>
      </section>

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

      <div className="dashboard-columns">
        <div className="dashboard-column">
          <section className="panel surface-card">
            <div className="section-header">
              <div className="section-title">
                <AppIcon className="icon-md icon-brand" name="chart" />
                <span>{t("home.subskillProgress")}</span>
              </div>
              <Link className="section-link" href="/progress">
                {t("home.viewDetails")} <AppIcon className="icon-sm" name="arrow-right" />
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
                      <div className="progress-bar">
                        <span style={{ width: `${percent}%` }} />
                      </div>
                    </div>
                    <div className="skill-side">
                      <span>{t("home.level")} {payload?.level ?? "-"}</span>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="panel surface-card">
            <div className="section-header">
              <div className="section-title">
                <AppIcon className="icon-md icon-brand" name="clipboard" />
                <span>{t("home.latestSummary")}</span>
              </div>
              <Link
                className="section-link"
                href={latestHistory ? `/records/${latestHistory.session_id}/review` : "/records"}
              >
                {t("home.viewFullRecord")} <AppIcon className="icon-sm" name="arrow-right" />
              </Link>
            </div>
            <div className="summary-layout">
              <div className="summary-thumb-wrap">
                <ThumbnailArtwork className="summary-thumb" variant="presentation" />
                <span className="summary-thumb-label">{t("home.scenarioPreview")}</span>
              </div>
              <div className="summary-meta">
                <div className="summary-line">
                  <AppIcon className="icon-sm icon-brand" name="tag" />
                  <span>{t("home.scenarioName")}</span>
                  <span>:</span>
                  <strong>{latestHistory?.scenario_title ?? t("home.noRecord")}</strong>
                </div>
                <div className="summary-line">
                  <AppIcon className="icon-sm icon-brand" name="star" />
                  <span>{t("home.score")}</span>
                  <span>:</span>
                  <strong className="score-text">{latestHistory ? latestHistory.overall_score : "-"} <span>/ 100</span></strong>
                </div>
                <div className="summary-line">
                  <AppIcon className="icon-sm icon-warn" name="spark" />
                  <span>{t("home.mainWeakness")}</span>
                  <span>:</span>
                  <strong>
                    {progress?.coach_memory.summary ?? t("home.defaultWeakness")}
                  </strong>
                </div>
                <div className="summary-line">
                  <AppIcon className="icon-sm icon-brand" name="lightbulb" />
                  <span>{t("home.nextSteps")}</span>
                  <span>:</span>
                  <strong>{progress?.coach_memory.next_actions?.[0] ?? t("progress.defaultNextAction")}</strong>
                </div>
              </div>
            </div>
          </section>
        </div>

        <div className="dashboard-column">
          <section className="panel surface-card">
            <div className="section-header">
              <div className="section-title">
                <AppIcon className="icon-md icon-brand" name="star" />
                <span>{t("home.todayRecommended")}</span>
              </div>
              <button className="section-link" onClick={() => void loadDashboard(activeLearnerId)} type="button">
                {t("home.refresh")} <AppIcon className="icon-sm" name="refresh" />
              </button>
            </div>
            <div className="recommend-stack">
              {recommendedRows.length === 0 ? (
                <div className="placeholder-inline">{t("home.noRecommendYet")}</div>
              ) : (
                recommendedRows.map((item) => (
                  <article className="recommend-row" key={item.scenario_id}>
                    <ThumbnailArtwork
                      className="recommend-thumb"
                      variant={scenarioArtVariant(item.scenario_id, item.target_subskills)}
                    />
                    <div className="recommend-body">
                      <h3>{item.title}</h3>
                      <p>{t("home.difficultyLabel")}{difficultyStars(item.difficulty)}</p>
                      <small>
                        {t("home.focusTraining")}{item.target_subskills.map((skill) => subskillLabel(skill)).join(", ")}
                      </small>
                    </div>
                    <button
                      className="icon-arrow-button"
                      disabled={startingScenarioId === item.scenario_id}
                      onClick={() => void startTraining(item.scenario_id)}
                      type="button"
                    >
                      <AppIcon className="icon-sm" name="arrow-right" />
                    </button>
                  </article>
                ))
              )}
            </div>
          </section>

          <section className="panel surface-card">
            <div className="section-header">
              <div className="section-title">
                <AppIcon className="icon-md icon-brand" name="trend" />
                <span>{t("home.growthTrend")}</span>
              </div>
              <div className="section-select">
                <select defaultValue="week">
                  <option value="week">{t("home.thisWeek")}</option>
                  <option value="month">{t("home.thisMonth")}</option>
                </select>
                <AppIcon className="icon-sm" name="chevron-down" />
              </div>
            </div>
            <div className="trend-layout">
              <div className="trend-chart-card">
                <svg className="trend-chart" viewBox="0 0 320 180" preserveAspectRatio="none">
                  <polyline points={sparklinePoints(trendScores.length ? trendScores : [45, 58, 63, 57, 61, 59], 320, 140)} />
                  <circle cx="16" cy="110" r="4" fill="#fff" stroke="#2f73ff" strokeWidth="2" />
                  <circle cx="64" cy="90" r="4" fill="#fff" stroke="#2f73ff" strokeWidth="2" />
                  <circle cx="112" cy="70" r="4" fill="#fff" stroke="#2f73ff" strokeWidth="2" />
                  <circle cx="160" cy="85" r="4" fill="#fff" stroke="#2f73ff" strokeWidth="2" />
                  <circle cx="208" cy="75" r="4" fill="#fff" stroke="#2f73ff" strokeWidth="2" />
                  <circle cx="256" cy="80" r="4" fill="#fff" stroke="#2f73ff" strokeWidth="2" />
                </svg>
                <div className="trend-axis">
                  <span>{t("home.weekdays.mon")}</span>
                  <span>{t("home.weekdays.tue")}</span>
                  <span>{t("home.weekdays.wed")}</span>
                  <span>{t("home.weekdays.thu")}</span>
                  <span>{t("home.weekdays.fri")}</span>
                  <span>{t("home.weekdays.sat")}</span>
                  <span>{t("home.weekdays.sun")}</span>
                </div>
              </div>
              <div className="trend-stats">
                <article>
                  <AppIcon className="icon-lg icon-brand" name="calendar" />
                  <div>
                    <span>{t("home.sessionsThisWeek")}</span>
                    <strong>{progress?.recent_history.length ?? 0} <small>{t("home.times")}</small></strong>
                  </div>
                </article>
                <article>
                  <AppIcon className="icon-lg icon-brand" name="target" />
                  <div>
                    <span>{t("home.averageScore")}</span>
                    <strong className="success-text">{averageScore || 0} <small>{t("home.pts")}</small></strong>
                  </div>
                </article>
                <article>
                  <AppIcon className="icon-lg icon-brand" name="shield" />
                  <div>
                    <span>{t("home.currentLevel")}</span>
                    <strong>Lv. {progress?.level ?? "-"} <small>{t("home.proficient")}</small></strong>
                  </div>
                </article>
              </div>
            </div>
          </section>
        </div>
      </div>

      {/* Cross-skill installed skills */}
      {crossSkills.length > 0 && (
        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="grid" />
              <span>{t("home.installedSkills")}</span>
            </div>
            <Link className="section-link" href="/marketplace">
              {t("home.manageSkills")} <AppIcon className="icon-sm" name="arrow-right" />
            </Link>
          </div>
          <div className="quick-entry-grid">
            {crossSkills.map((skill) => (
              <article key={skill.skill_id} className="quick-entry-card" style={{ gap: "0.75rem" }}>
                <AppIcon className="icon-lg icon-brand" name="grid" />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <strong style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {skill.skill_name}
                  </strong>
                  <p style={{ fontSize: "0.8rem", color: skill.progress?.has_progress ? "#059669" : "#9ca3af", margin: 0 }}>
                    {skill.progress?.has_progress
                      ? `${t("home.skillSessions", { count: skill.progress.total_sessions ?? 0 })} · ${t("home.skillScore", { score: skill.progress.overall_score ?? "-" })}`
                      : t("home.noSessionsYet")}
                  </p>
                </div>
                <AppIcon className="icon-sm" name="arrow-right" />
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="panel surface-card">
        <div className="section-header">
          <div className="section-title">
            <AppIcon className="icon-md icon-brand" name="rocket" />
            <span>{t("home.quickLinks")}</span>
          </div>
        </div>
        <div className="quick-entry-grid">
          <Link
            className="quick-entry-card"
            href={latestHistory ? `/records/${latestHistory.session_id}/review` : "/scenarios"}
          >
            <div className="quick-entry-icon">
              <AppIcon className="icon-lg icon-brand" name="play" />
            </div>
            <div>
              <strong>{t("home.continueTraining")}</strong>
              <p>{latestHistory?.scenario_title ?? t("home.startFromList")}</p>
            </div>
            <AppIcon className="icon-sm" name="arrow-right" />
          </Link>

          <Link className="quick-entry-card" href={latestHistory ? `/records/${latestHistory.session_id}/review` : "/records"}>
            <div className="quick-entry-icon">
              <AppIcon className="icon-lg icon-brand" name="clipboard" />
            </div>
            <div>
              <strong>{t("home.viewReview")}</strong>
              <p>{t("home.viewReviewDesc")}</p>
            </div>
            <AppIcon className="icon-sm" name="arrow-right" />
          </Link>

          <Link className="quick-entry-card" href="/progress">
            <div className="quick-entry-icon">
              <AppIcon className="icon-lg icon-brand" name="trend" />
            </div>
            <div>
              <strong>{t("home.viewProgress")}</strong>
              <p>{t("home.viewProgressDesc")}</p>
            </div>
            <AppIcon className="icon-sm" name="arrow-right" />
          </Link>
        </div>
      </section>
    </section>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { AppIcon } from "@/components/app-graphics";
import { formatTimestamp, subskillLabel } from "@/lib/mr-ui";
import {
  fetchCrossSkillDashboard,
  type CrossSkillDashboardEntry,
  readOrganizationReports,
  type AttentionReason,
  type OrganizationReportsResponse,
} from "@/lib/runtime-api";

type TeamFlowProps = {
  initialOrganizationId: string;
  viewerRole?: string | null;
};

function attentionReasonLabel(
  reason: AttentionReason,
  t: (key: string) => string
): string {
  switch (reason.code) {
    case "high_compliance_risk":
      return t("team.reasonHighCompliance");
    case "medium_compliance_risk":
      return t("team.reasonMediumCompliance");
    case "low_average_score":
      return t("team.reasonLowAverage");
    case "low_latest_score":
      return t("team.reasonLowLatest");
    case "low_completion_rate":
      return t("team.reasonLowCompletion");
    case "recurring_weakness":
      return reason.subskill_id
        ? `${t("team.reasonRecurringWeakness")}: ${subskillLabel(reason.subskill_id)}`
        : t("team.reasonRecurringWeakness");
    default:
      return reason.detail;
  }
}

function riskTone(severity: string | null | undefined): "high" | "medium" | "low" | "none" {
  switch (severity) {
    case "critical":
    case "high":
      return "high";
    case "medium":
      return "medium";
    case "low":
      return "low";
    default:
      return "none";
  }
}

function riskLabel(severity: string | null | undefined, t: (key: string) => string): string {
  switch (riskTone(severity)) {
    case "high":
      return t("team.highRisk");
    case "medium":
      return t("team.mediumRisk");
    case "low":
      return t("team.lowRisk");
    default:
      return t("team.noRisk");
  }
}

export function TeamFlow({
  initialOrganizationId,
  viewerRole = "supervisor",
}: TeamFlowProps) {
  const { t } = useTranslation();
  const organizationId = initialOrganizationId.trim() || "local";

  const [payload, setPayload] = useState<OrganizationReportsResponse | null>(null);
  const [crossSkills, setCrossSkills] = useState<CrossSkillDashboardEntry[]>([]);
  const [skillFilter, setSkillFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const buildContextHref = (
    pathname: string,
    extraParams: Record<string, string | null | undefined> = {}
  ): string => {
    const searchParams = new URLSearchParams();
    if (organizationId) {
      searchParams.set("org", organizationId);
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
    let active = true;
    const loadReports = async () => {
      setLoading(true);
      setError(null);
      try {
        const nextPayload = await readOrganizationReports(organizationId, {
          orgId: organizationId,
          viewerRole,
        });
        if (active) {
          setPayload(nextPayload);
        }
      } catch (loadError) {
        if (active) {
          setPayload(null);
          setError(loadError instanceof Error ? loadError.message : "Unknown team loading error");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
      try {
        const dash = await fetchCrossSkillDashboard(organizationId);
        if (active) {
          setCrossSkills(dash.skills);
        }
      } catch {
        if (active) setCrossSkills([]);
      }
    };
    void loadReports();
    return () => {
      active = false;
    };
  }, [organizationId, viewerRole]);

  const atRiskLearners = useMemo(
    () => (payload?.learners ?? []).filter((learner) => learner.needs_attention),
    [payload]
  );

  const isPermissionError = error && /403|forbidden|restricted|denied/i.test(error);

  if (loading) {
    return (
      <section className="dashboard-page">
        <div className="placeholder-block surface-card">
          <strong>{t("team.loading")}</strong>
          <p>{t("team.loadingDesc")}</p>
        </div>
      </section>
    );
  }

  if (!payload) {
    return (
      <section className="dashboard-page">
        {error ? (
          <div className="error-banner">
            {isPermissionError ? t("restricted.summaryOnly") : error}
          </div>
        ) : null}
        <div className="placeholder-block surface-card">
          <strong>{isPermissionError ? t("restricted.progressDetail") : t("team.noData")}</strong>
          <p>{isPermissionError ? t("restricted.contactAdmin") : t("team.noDataDesc")}</p>
          <div className="placeholder-actions">
            <Link className="primary-button" href="/records">
              {t("nav.records")}
            </Link>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="dashboard-page">
      <section className="hero-panel surface-card">
        <div className="hero-panel-main">
          <div className="hero-icon-tile">
            <AppIcon className="icon-xl icon-brand" name="doctor" />
          </div>
          <div className="hero-panel-copy">
            <h1>{t("team.pageTitle")}</h1>
            <p>{t("team.pageSubtitle")}</p>
            <div className="team-hero-meta">
              <span className="section-chip">
                {payload.organization_scope === "organization"
                  ? t("team.orgScopeOrganization")
                  : t("team.orgScopeGlobal")}
              </span>
              <span className="section-chip">
                {t("team.generatedAt")} {formatTimestamp(payload.generated_at)}
              </span>
            </div>
          </div>
        </div>
        <Link className="primary-button hero-button" href={buildContextHref("/team")}>
          <AppIcon className="icon-sm" name="refresh" />
          <span>{t("team.refresh")}</span>
        </Link>
      </section>

      {error ? (
        <div className="error-banner">
          {isPermissionError ? t("restricted.summaryOnly") : error}
        </div>
      ) : null}

      <section className="team-summary-grid">
        <article className="team-summary-card surface-card">
          <span>{t("team.totalLearners")}</span>
          <strong>{payload.team_summary.learner_count}</strong>
          <small>
            {payload.team_summary.total_sessions} {t("team.sessions")}
          </small>
        </article>
        <article className="team-summary-card surface-card">
          <span>{t("team.averageScore")}</span>
          <strong>{payload.team_summary.average_score ?? "-"}</strong>
          <small>{payload.team_summary.finalized_sessions} {t("team.finalizedSessions")}</small>
        </article>
        <article className="team-summary-card surface-card">
          <span>{t("team.practiceCompletion")}</span>
          <strong>{Math.round(payload.team_summary.practice_completion_rate * 100)}%</strong>
          <small>{payload.team_summary.active_sessions} {t("team.activeSessions")}</small>
        </article>
        <article className="team-summary-card surface-card warn">
          <span>{t("team.atRiskLearners")}</span>
          <strong>{payload.team_summary.at_risk_learner_count}</strong>
          <small>{payload.team_summary.high_risk_session_count} {t("team.highRiskSessions")}</small>
        </article>
      </section>

      {crossSkills.length > 0 ? (
        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="grid" />
              <span>{t("home.installedSkills")}</span>
            </div>
            {crossSkills.length > 1 ? (
              <div className="section-select">
                <select
                  defaultValue="all"
                  onChange={(e) => setSkillFilter(e.target.value)}
                >
                  <option value="all">{t("records.allSkills")}</option>
                  {crossSkills.map((s) => (
                    <option key={s.skill_id} value={s.skill_id}>{s.skill_name}</option>
                  ))}
                </select>
                <AppIcon className="icon-sm" name="chevron-down" />
              </div>
            ) : null}
          </div>
          <div className="quick-entry-grid">
            {(skillFilter === "all"
              ? crossSkills
              : crossSkills.filter((s) => s.skill_id === skillFilter)
            ).map((skill) => (
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
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <div className="review-grid-two">
        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="spark" />
              <span>{t("team.recurringWeaknesses")}</span>
            </div>
          </div>
          <div className="team-weakness-list">
            {payload.team_summary.recurring_weaknesses.length === 0 ? (
              <div className="placeholder-inline">{t("team.noWeaknesses")}</div>
            ) : (
              payload.team_summary.recurring_weaknesses.map((item) => (
                <article className="team-weakness-row" key={item.subskill_id}>
                  <strong>{subskillLabel(item.subskill_id)}</strong>
                  <span>{item.occurrences}x</span>
                  <small>
                    {item.affected_learners} {t("team.affectedLearners")}
                  </small>
                </article>
              ))
            )}
          </div>
        </section>

        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="alert" />
              <span>{t("team.learnersNeedingHelp")}</span>
            </div>
          </div>
          <div className="team-alert-list">
            {atRiskLearners.length === 0 ? (
              <div className="placeholder-inline">{t("team.noLearnersNeedHelp")}</div>
            ) : (
              atRiskLearners.slice(0, 4).map((learner) => (
                <article className="team-alert-row" key={learner.learner_id}>
                  <div>
                    <strong>{learner.learner_id}</strong>
                    <p>
                      {learner.needs_attention_reasons
                        .slice(0, 2)
                        .map((item) => attentionReasonLabel(item, t))
                        .join(" · ")}
                    </p>
                  </div>
                  <Link
                    className="section-link"
                    href={buildContextHref("/progress", { learner: learner.learner_id })}
                  >
                    {t("team.viewLearner")}
                  </Link>
                </article>
              ))
            )}
          </div>
        </section>
      </div>

      <section className="panel surface-card">
        <div className="section-header">
          <div className="section-title">
            <AppIcon className="icon-md icon-brand" name="list" />
            <span>{t("team.learnerBreakdown")}</span>
          </div>
        </div>
        <div className="team-learner-grid">
          {payload.learners.map((learner) => {
            const latestReview = learner.recent_reviews[0] ?? null;
            const risk = riskTone(learner.highest_compliance_severity);

            return (
              <article className="team-learner-card" key={learner.learner_id}>
                <div className="team-learner-head">
                  <div>
                    <h3>{learner.learner_id}</h3>
                    <p>{learner.latest_scenario_title ?? t("team.noLatestScenario")}</p>
                  </div>
                  <span className={`team-status-badge ${learner.needs_attention ? "warn" : "success"}`}>
                    {learner.needs_attention ? t("team.needsAttention") : t("team.onTrack")}
                  </span>
                </div>

                <div className="team-learner-metrics">
                  <div>
                    <span>{t("team.averageScore")}</span>
                    <strong>{learner.average_score ?? "-"}</strong>
                  </div>
                  <div>
                    <span>{t("team.practiceCompletion")}</span>
                    <strong>{Math.round(learner.practice_completion_rate * 100)}%</strong>
                  </div>
                  <div>
                    <span>{t("team.complianceRisk")}</span>
                    <strong className={`risk-${risk}`}>{riskLabel(learner.highest_compliance_severity, t)}</strong>
                  </div>
                </div>

                <div className="tag-list">
                  {learner.active_focus_subskills.slice(0, 4).map((skillId) => (
                    <span className="skill-tag" key={skillId}>
                      {subskillLabel(skillId)}
                    </span>
                  ))}
                </div>

                <div className="team-reason-list">
                  {learner.needs_attention_reasons.length === 0 ? (
                    <span className="team-reason-chip success">{t("team.noImmediateAction")}</span>
                  ) : (
                    learner.needs_attention_reasons.slice(0, 3).map((reason, index) => (
                      <span className="team-reason-chip" key={`${learner.learner_id}-${reason.code}-${index}`}>
                        {attentionReasonLabel(reason, t)}
                      </span>
                    ))
                  )}
                </div>

                <div className="team-review-stack">
                  <strong>{t("team.recentReviews")}</strong>
                  {learner.recent_reviews.length === 0 ? (
                    <div className="placeholder-inline">{t("team.noReviews")}</div>
                  ) : (
                    learner.recent_reviews.slice(0, 2).map((review) => (
                      <div className="team-review-row" key={review.session_id}>
                        <div>
                          <span>{review.scenario_title}</span>
                          <small>
                            {formatTimestamp(review.updated_at)}
                            {review.overall_score !== null && review.overall_score !== undefined
                              ? ` · ${review.overall_score}/100`
                              : ""}
                          </small>
                        </div>
                        <Link
                          className="section-link"
                          href={buildContextHref(`/records/${review.session_id}/review`)}
                        >
                          {t("team.viewReview")}
                        </Link>
                      </div>
                    ))
                  )}
                </div>

                <div className="team-learner-actions">
                  <Link
                    className="ghost-button"
                    href={buildContextHref("/progress", { learner: learner.learner_id })}
                  >
                    {t("team.viewLearner")}
                  </Link>
                  {latestReview ? (
                    <Link
                      className="primary-button"
                      href={buildContextHref(`/records/${latestReview.session_id}/review`)}
                    >
                      {t("team.latestReview")}
                    </Link>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </section>
  );
}

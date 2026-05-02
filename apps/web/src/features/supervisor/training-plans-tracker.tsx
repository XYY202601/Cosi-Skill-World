"use client";

import { useEffect, useState } from "react";

import { AppIcon } from "@/components/app-graphics";
import { formatTimestamp, subskillLabel } from "@/lib/mr-ui";
import {
  listTrainingPlans,
  readOrganizationReports,
  type TrainingPlanItem,
  type OrganizationReportsResponse,
} from "@/lib/runtime-api";

type EnhancedPlan = TrainingPlanItem & {
  learnerSummaries: Array<{
    learner_id: string;
    total_sessions: number;
    average_score: number | null;
    last_score: number | null;
    needs_attention: boolean;
  }>;
};

type TrainingPlansTrackerProps = {
  organizationId: string;
  viewerRole?: string | null;
};

export function TrainingPlansTracker({
  organizationId,
  viewerRole = "supervisor",
}: TrainingPlansTrackerProps) {
  const [plans, setPlans] = useState<EnhancedPlan[]>([]);
  const [report, setReport] = useState<OrganizationReportsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedPlan, setExpandedPlan] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const context = { orgId: organizationId, viewerRole };
        const [planResult, reportResult] = await Promise.allSettled([
          listTrainingPlans(context),
          readOrganizationReports(organizationId, context),
        ]);

        const planResponse = planResult.status === "fulfilled" ? planResult.value : null;
        const reportResponse = reportResult.status === "fulfilled" ? reportResult.value : null;

        const learnerMap = new Map(
          (reportResponse?.learners ?? []).map((learner) => [
            learner.learner_id,
            {
              learner_id: learner.learner_id,
              total_sessions: learner.total_sessions,
              average_score: learner.average_score ?? null,
              last_score: learner.last_score ?? null,
              needs_attention: learner.needs_attention,
            },
          ]),
        );

        const enriched: EnhancedPlan[] = (planResponse?.plans ?? [])
          .filter((plan) => plan.status === "active")
          .map((plan) => ({
            ...plan,
            learnerSummaries: plan.assigned_learners
              .map((learnerId) => learnerMap.get(learnerId))
              .filter((summary): summary is NonNullable<typeof summary> => summary !== undefined),
          }));

        if (active) {
          setPlans(enriched);
          setReport(reportResponse);
          if (!planResponse && !reportResponse) {
            const planError =
              planResult.status === "rejected" ? planResult.reason : null;
            const reportError =
              reportResult.status === "rejected" ? reportResult.reason : null;
            const failure = planError ?? reportError;
            setError(
              failure instanceof Error ? failure.message : "Failed to load training plan data",
            );
          }
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    void loadData();
    return () => {
      active = false;
    };
  }, [organizationId, viewerRole]);

  if (loading) {
    return (
      <section className="panel surface-card">
        <div className="placeholder-block">
          <strong>Training Plans</strong>
          <p>Loading progress data...</p>
        </div>
      </section>
    );
  }

  const learners = report?.learners ?? [];
  const learnersWithActivity = learners.filter((learner) => learner.total_sessions > 0);
  const atRiskLearners = learners.filter((learner) => learner.needs_attention);
  const latestActivity = learners
    .map((learner) => learner.latest_session_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1);

  return (
    <section className="panel surface-card">
      <div className="section-header">
        <div className="section-title">
          <AppIcon className="icon-md icon-brand" name="flag" />
          <span>Training Data & Plans</span>
        </div>
      </div>

      {error ? <div className="error-banner">{error}</div> : null}

      <div className="team-plan-summary-grid">
        <article className="team-summary-card surface-card">
          <span>Active plans</span>
          <strong>{plans.length}</strong>
          <small>{learnersWithActivity.length} learners with training records</small>
        </article>
        <article className="team-summary-card surface-card">
          <span>Total sessions</span>
          <strong>{report?.team_summary.total_sessions ?? 0}</strong>
          <small>{report?.team_summary.finalized_sessions ?? 0} finalized</small>
        </article>
        <article className="team-summary-card surface-card warn">
          <span>Needs attention</span>
          <strong>{atRiskLearners.length}</strong>
          <small>{report?.team_summary.high_risk_session_count ?? 0} high-risk sessions</small>
        </article>
        <article className="team-summary-card surface-card">
          <span>Latest activity</span>
          <strong>{latestActivity ? formatTimestamp(latestActivity) : "-"}</strong>
          <small>{organizationId} organization scope</small>
        </article>
      </div>

      {!plans.length ? (
        <div className="placeholder-block">
          <strong>No active training plans yet</strong>
          <p>
            Training data is now shown below even without a plan. Create a plan if you want to
            assign goals, scenarios, and learner cohorts.
          </p>
        </div>
      ) : (
        <div className="team-plan-list">
          {plans.map((plan) => {
            const isExpanded = expandedPlan === plan.plan_id;
            const atRiskCount = plan.learnerSummaries.filter((summary) => summary.needs_attention).length;
            const avgScoreAcrossLearners = plan.learnerSummaries.length > 0
              ? plan.learnerSummaries.reduce((sum, summary) => sum + (summary.average_score ?? 0), 0) / plan.learnerSummaries.length
              : null;

            return (
              <article
                className={`team-plan-card ${isExpanded ? "is-expanded" : ""}`}
                key={plan.plan_id}
              >
                <div className="team-plan-head" onClick={() => setExpandedPlan(isExpanded ? null : plan.plan_id)}>
                  <div className="team-plan-head-left">
                    <h3>{plan.title}</h3>
                    <p className="team-plan-meta">
                      {plan.plan_id} · v{plan.version} · {plan.target_subskills.join(", ") || "no subskills"}
                    </p>
                  </div>
                  <div className="team-plan-head-right">
                    <span className="team-stat-chip">
                      {plan.learnerSummaries.length} learners
                    </span>
                    {avgScoreAcrossLearners !== null ? (
                      <span className="team-stat-chip">
                        Avg: {avgScoreAcrossLearners.toFixed(1)}
                      </span>
                    ) : null}
                    {atRiskCount > 0 ? (
                      <span className="team-stat-chip warn">{atRiskCount} at risk</span>
                    ) : null}
                  </div>
                </div>

                {isExpanded && (
                  <div className="team-plan-body">
                    <div className="team-plan-goal">
                      <strong>Goal:</strong> {plan.goal_criteria}
                      {plan.due_date ? <span> · Due: {plan.due_date}</span> : null}
                    </div>

                    {plan.learnerSummaries.length > 0 ? (
                      <div className="team-plan-learner-grid">
                        {plan.learnerSummaries.map((summary) => (
                          <div
                            className={`team-plan-learner-row ${summary.needs_attention ? "warn" : ""}`}
                            key={summary.learner_id}
                          >
                            <div className="team-plan-learner-info">
                              <strong>{summary.learner_id}</strong>
                              <span>
                                {summary.total_sessions} sessions · Avg: {summary.average_score?.toFixed(1) ?? "-"}
                              </span>
                            </div>
                            <span
                              className={`team-status-badge ${summary.needs_attention ? "warn" : "success"}`}
                            >
                              {summary.needs_attention ? "Needs attention" : "On track"}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="placeholder-inline">No assigned learners have session data yet.</div>
                    )}

                    <div className="team-plan-footer">
                      <small>Created: {formatTimestamp(plan.created_at)}</small>
                      <small>Updated: {formatTimestamp(plan.updated_at)}</small>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}

      <div className="team-plan-learner-grid">
        {learnersWithActivity.length > 0 ? (
          learnersWithActivity.slice(0, 8).map((learner) => (
            <article className="team-plan-learner-card" key={learner.learner_id}>
              <div className="team-plan-learner-card-head">
                <div>
                  <strong>{learner.learner_id}</strong>
                  <span>{learner.latest_scenario_title ?? "No latest scenario title"}</span>
                </div>
                <span
                  className={`team-status-badge ${learner.needs_attention ? "warn" : "success"}`}
                >
                  {learner.needs_attention ? "Needs attention" : "Active"}
                </span>
              </div>

              <div className="team-plan-learner-card-metrics">
                <span>{learner.total_sessions} sessions</span>
                <span>Avg {learner.average_score?.toFixed(1) ?? "-"}</span>
                <span>Last {learner.last_score?.toFixed(1) ?? "-"}</span>
              </div>

              <div className="team-plan-learner-card-tags">
                {(learner.active_focus_subskills.length > 0
                  ? learner.active_focus_subskills
                  : learner.recurring_weaknesses.map((item) => item.subskill_id)
                )
                  .slice(0, 3)
                  .map((subskillId) => (
                    <span className="team-stat-chip" key={subskillId}>
                      {subskillLabel(subskillId)}
                    </span>
                  ))}
              </div>

              <small>
                Updated {learner.latest_session_at ? formatTimestamp(learner.latest_session_at) : "-"}
              </small>
            </article>
          ))
        ) : (
          <div className="placeholder-inline">
            No learner training sessions are available for this organization yet.
          </div>
        )}
      </div>
    </section>
  );
}

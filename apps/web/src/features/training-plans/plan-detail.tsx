"use client";

import { useEffect, useState } from "react";

import { AppIcon } from "@/components/app-graphics";
import { formatTimestamp } from "@/lib/mr-ui";
import {
  getTrainingPlan,
  getTrainingPlanProgress,
  type TrainingPlanItem,
  type PlanProgressResponse,
} from "@/lib/runtime-api";

function statusColor(status: string): string {
  if (status === "achieved") return "#22c55e";
  if (status === "partially_achieved") return "#f59e0b";
  return "#ef4444";
}

function statusBadgeClass(status: string): string {
  if (status === "active") return "section-chip";
  if (status === "completed") return "section-chip success-chip";
  if (status === "paused") return "section-chip warn-chip";
  return "section-chip";
}

type PlanDetailProps = {
  planId: string;
};

export function PlanDetail({ planId }: PlanDetailProps) {
  const [plan, setPlan] = useState<TrainingPlanItem | null>(null);
  const [progress, setProgress] = useState<PlanProgressResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [planData, progressData] = await Promise.all([
          getTrainingPlan(planId),
          getTrainingPlanProgress(planId),
        ]);
        setPlan(planData);
        setProgress(progressData);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load plan");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [planId]);

  if (loading) {
    return (
      <section className="dashboard-page">
        <div className="placeholder-block surface-card">
          <strong>Loading...</strong>
          <p>Loading training plan details.</p>
        </div>
      </section>
    );
  }

  if (error || !plan) {
    return (
      <section className="dashboard-page">
        <div className="placeholder-block surface-card">
          <strong>Error</strong>
          <p>{error ?? "Plan not found."}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="dashboard-page">
      <section className="hero-panel surface-card">
        <div className="hero-panel-main">
          <div className="hero-icon-tile">
            <AppIcon className="icon-xl icon-brand" name="target" />
          </div>
          <div className="hero-panel-copy">
            <h1>{plan.title}</h1>
            <p>{plan.description || "No description."}</p>
            <div className="admin-hero-meta">
              <span className={statusBadgeClass(plan.status)}>{plan.status}</span>
              <span className="section-chip">{plan.target_subskills.length} subskills</span>
              <span className="section-chip">{plan.assigned_learners.length} learners</span>
            </div>
          </div>
        </div>
      </section>

      <section className="panel surface-card">
        <div className="section-header">
          <div className="section-title">
            <AppIcon className="icon-md icon-brand" name="flag" />
            <span>Plan Overview</span>
          </div>
        </div>
        <div className="admin-plan-detail-grid">
          <div className="admin-plan-detail-item">
            <strong>Goal Criteria</strong>
            <p>{plan.goal_criteria}</p>
          </div>
          <div className="admin-plan-detail-item">
            <strong>Success Threshold</strong>
            <p>{plan.success_threshold}+</p>
          </div>
          {plan.due_date ? (
            <div className="admin-plan-detail-item">
              <strong>Due Date</strong>
              <p>{plan.due_date}</p>
            </div>
          ) : null}
          <div className="admin-plan-detail-item">
            <strong>Review Cadence</strong>
            <p>{plan.review_cadence}</p>
          </div>
        </div>
        {plan.target_subskills.length > 0 ? (
          <div className="admin-plan-detail-item" style={{ marginTop: 12 }}>
            <strong>Target Subskills</strong>
            <div className="admin-plan-tag-row">
              {plan.target_subskills.map((s) => (
                <span className="skill-tag" key={s}>{s}</span>
              ))}
            </div>
          </div>
        ) : null}
        {plan.required_scenario_ids.length > 0 ? (
          <div className="admin-plan-detail-item" style={{ marginTop: 12 }}>
            <strong>Required Scenarios</strong>
            <div className="admin-plan-tag-row">
              {plan.required_scenario_ids.map((s) => (
                <span className="skill-tag" key={s}>{s}</span>
              ))}
            </div>
          </div>
        ) : null}
        <div className="admin-plan-footer" style={{ marginTop: 12 }}>
          <small>Plan ID: {plan.plan_id}</small>
          <small>Created: {formatTimestamp(plan.created_at)}</small>
          <small>Updated: {formatTimestamp(plan.updated_at)}</small>
          <small>v{plan.version}</small>
        </div>
      </section>

      {progress ? (
        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="chart" />
              <span>Learner Progress</span>
            </div>
            <span className="section-chip">
              Overall: {(progress.overall_achievement_rate * 100).toFixed(0)}%
            </span>
          </div>
          {progress.learners.length === 0 ? (
            <div className="placeholder-block">
              <strong>No learners assigned</strong>
              <p>Assign learners to this plan to track their progress here.</p>
            </div>
          ) : (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Learner</th>
                    <th>Sessions</th>
                    <th>Finalized</th>
                    {plan.target_subskills.map((s) => (
                      <th key={s}>{s}</th>
                    ))}
                    <th>Status</th>
                    <th>Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {progress.learners.map((row) => (
                    <tr key={row.learner_id}>
                      <td className="admin-table-id">{row.learner_id}</td>
                      <td>{row.total_sessions}</td>
                      <td>{row.finalized_sessions}</td>
                      {plan.target_subskills.map((s) => (
                        <td key={s}>
                          <span style={{
                            color: (row.subskill_scores[s] ?? 0) >= plan.success_threshold
                              ? "#22c55e" : "#ef4444",
                          }}>
                            {(row.subskill_scores[s] ?? 0).toFixed(1)}
                          </span>
                        </td>
                      ))}
                      <td>
                        <span style={{ color: statusColor(row.achievement_status) }}>
                          {row.achievement_status}
                        </span>
                      </td>
                      <td>{(row.achievement_rate * 100).toFixed(0)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}
    </section>
  );
}

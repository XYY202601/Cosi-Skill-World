"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { AppIcon } from "@/components/app-graphics";
import { TagInput } from "@/components/tag-input";
import { formatTimestamp } from "@/lib/mr-ui";
import {
  listTrainingPlans,
  createTrainingPlan,
  updateTrainingPlan,
  deleteTrainingPlan,
  assignLearnersToPlan,
  unassignLearnersFromPlan,
  type TrainingPlanItem,
} from "@/lib/runtime-api";

type PlanFormData = {
  title: string;
  description: string;
  org_id: string;
  owner_id: string;
  target_subskills: string[];
  required_scenario_ids: string[];
  assigned_learners: string[];
  assigned_cohorts: string[];
  goal_criteria: string;
  success_threshold: number;
  due_date: string;
  status: string;
};

const EMPTY_FORM: PlanFormData = {
  title: "",
  description: "",
  org_id: "default",
  owner_id: "",
  target_subskills: [],
  required_scenario_ids: [],
  assigned_learners: [],
  assigned_cohorts: [],
  goal_criteria: "",
  success_threshold: 4.0,
  due_date: "",
  status: "active",
};

export function TrainingPlansFlow() {
  const { t } = useTranslation();
  const [plans, setPlans] = useState<TrainingPlanItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingPlanId, setEditingPlanId] = useState<string | null>(null);
  const [formData, setFormData] = useState<PlanFormData>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [assignInput, setAssignInput] = useState<Record<string, string>>({});

  const loadPlans = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await listTrainingPlans();
      setPlans(response.plans);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load training plans");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPlans();
  }, []);

  const resetForm = () => {
    setFormData(EMPTY_FORM);
    setEditingPlanId(null);
    setShowForm(false);
  };

  const openEditForm = (plan: TrainingPlanItem) => {
    setFormData({
      title: plan.title,
      description: plan.description,
      org_id: plan.org_id,
      owner_id: plan.owner_id,
      target_subskills: plan.target_subskills,
      required_scenario_ids: plan.required_scenario_ids,
      assigned_learners: plan.assigned_learners,
      assigned_cohorts: plan.assigned_cohorts,
      goal_criteria: plan.goal_criteria,
      success_threshold: plan.success_threshold,
      due_date: plan.due_date ?? "",
      status: plan.status,
    });
    setEditingPlanId(plan.plan_id);
    setShowForm(true);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        title: formData.title,
        description: formData.description,
        org_id: formData.org_id,
        owner_id: formData.owner_id,
        target_subskills: formData.target_subskills,
        required_scenario_ids: formData.required_scenario_ids,
        assigned_learners: formData.assigned_learners,
        assigned_cohorts: formData.assigned_cohorts,
        goal_criteria: formData.goal_criteria,
        success_threshold: formData.success_threshold,
        due_date: formData.due_date || null,
        status: formData.status,
      };
      if (editingPlanId) {
        await updateTrainingPlan(editingPlanId, payload);
      } else {
        await createTrainingPlan(payload);
      }
      resetForm();
      await loadPlans();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Failed to save training plan");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (planId: string) => {
    if (!confirm("Delete this training plan? This cannot be undone.")) return;
    try {
      await deleteTrainingPlan(planId);
      await loadPlans();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Failed to delete training plan");
    }
  };

  const handleAssign = async (planId: string) => {
    const input = assignInput[planId] ?? "";
    const learnerIds = input.split(",").map((s) => s.trim()).filter(Boolean);
    if (!learnerIds.length) return;
    try {
      await assignLearnersToPlan(planId, learnerIds);
      setAssignInput((prev) => ({ ...prev, [planId]: "" }));
      await loadPlans();
    } catch (assignError) {
      setError(assignError instanceof Error ? assignError.message : "Failed to assign learners");
    }
  };

  const handleUnassign = async (planId: string, learnerId: string) => {
    try {
      await unassignLearnersFromPlan(planId, [learnerId]);
      await loadPlans();
    } catch (unassignError) {
      setError(unassignError instanceof Error ? unassignError.message : "Failed to unassign learner");
    }
  };

  const activePlans = plans.filter((p) => p.status === "active");
  const pausedPlans = plans.filter((p) => p.status === "paused");

  if (loading && !plans.length) {
    return (
      <section className="dashboard-page">
        <div className="placeholder-block surface-card">
          <strong>{t("admin.loading")}</strong>
          <p>Loading training plans...</p>
        </div>
      </section>
    );
  }

  return (
    <section className="dashboard-page">
      <section className="hero-panel surface-card">
        <div className="hero-panel-main">
          <div className="hero-icon-tile">
            <AppIcon className="icon-xl icon-brand" name="clipboard" />
          </div>
          <div className="hero-panel-copy">
            <h1>Training Plans</h1>
            <p>Create and manage training plans with goal assignments for learners and cohorts.</p>
            <div className="admin-hero-meta">
              <span className="section-chip">{plans.length} total plans</span>
              <span className="section-chip">{activePlans.length} active</span>
            </div>
          </div>
        </div>
        <button className="primary-button hero-button" onClick={() => { resetForm(); setShowForm(true); }}>
          <AppIcon className="icon-sm" name="target" />
          <span>New Plan</span>
        </button>
      </section>

      {error ? <div className="error-banner">{error}</div> : null}

      {showForm ? (
        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="target" />
              <span>{editingPlanId ? "Edit Training Plan" : "Create Training Plan"}</span>
            </div>
            <button className="ghost-button" onClick={resetForm}>Cancel</button>
          </div>
          <div className="admin-form-grid">
            <label className="admin-field">
              <span>Title *</span>
              <input
                type="text"
                value={formData.title}
                onChange={(e) => setFormData((prev) => ({ ...prev, title: e.target.value }))}
                placeholder="e.g., Q1 Objection Handling Focus"
              />
            </label>
            <label className="admin-field">
              <span>Description</span>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData((prev) => ({ ...prev, description: e.target.value }))}
                placeholder="Optional description of the plan goals"
              />
            </label>
            <label className="admin-field">
              <span>Organization ID</span>
              <input
                type="text"
                value={formData.org_id}
                onChange={(e) => setFormData((prev) => ({ ...prev, org_id: e.target.value }))}
              />
            </label>
            <label className="admin-field">
              <span>Owner ID</span>
              <input
                type="text"
                value={formData.owner_id}
                onChange={(e) => setFormData((prev) => ({ ...prev, owner_id: e.target.value }))}
                placeholder="e.g., admin@org"
              />
            </label>
            <label className="admin-field">
              <span>Target Subskills</span>
              <TagInput
                value={formData.target_subskills}
                onChange={(tags) => setFormData((prev) => ({ ...prev, target_subskills: tags }))}
                placeholder="e.g., objection_handling, need_discovery"
              />
            </label>
            <label className="admin-field">
              <span>Required Scenario IDs</span>
              <TagInput
                value={formData.required_scenario_ids}
                onChange={(tags) => setFormData((prev) => ({ ...prev, required_scenario_ids: tags }))}
                placeholder="e.g., onco_skeptical_01"
              />
            </label>
            <label className="admin-field">
              <span>Assigned Learners</span>
              <TagInput
                value={formData.assigned_learners}
                onChange={(tags) => setFormData((prev) => ({ ...prev, assigned_learners: tags }))}
                placeholder="e.g., learner_01"
              />
            </label>
            <label className="admin-field">
              <span>Goal Criteria</span>
              <input
                type="text"
                value={formData.goal_criteria}
                onChange={(e) => setFormData((prev) => ({ ...prev, goal_criteria: e.target.value }))}
                placeholder="Achieve 4.0+ on all target subskills"
              />
            </label>
            <label className="admin-field">
              <span>Success Threshold</span>
              <input
                type="number"
                step="0.5"
                min="1"
                max="5"
                value={formData.success_threshold}
                onChange={(e) => setFormData((prev) => ({ ...prev, success_threshold: parseFloat(e.target.value) || 4.0 }))}
              />
            </label>
            <label className="admin-field">
              <span>Due Date</span>
              <input
                type="date"
                value={formData.due_date}
                onChange={(e) => setFormData((prev) => ({ ...prev, due_date: e.target.value }))}
              />
            </label>
            <label className="admin-field">
              <span>Status</span>
              <select
                value={formData.status}
                onChange={(e) => setFormData((prev) => ({ ...prev, status: e.target.value }))}
              >
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="completed">Completed</option>
                <option value="archived">Archived</option>
              </select>
            </label>
          </div>
          <div className="admin-form-actions">
            <button className="ghost-button" onClick={resetForm}>Cancel</button>
            <button
              className="primary-button"
              onClick={handleSave}
              disabled={saving || !formData.title.trim()}
            >
              {saving ? "Saving..." : editingPlanId ? "Update Plan" : "Create Plan"}
            </button>
          </div>
        </section>
      ) : null}

      {activePlans.length > 0 ? (
        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="flag" />
              <span>Active Plans ({activePlans.length})</span>
            </div>
          </div>
          <div className="admin-plan-list">
            {activePlans.map((plan) => (
              <article className="admin-plan-card" key={plan.plan_id}>
                <div className="admin-plan-head">
                  <div>
                    <h3>{plan.title}</h3>
                    <p className="admin-plan-meta">
                      {plan.plan_id} · {plan.target_subskills.join(", ") || "no subskills"} ·
                      threshold {plan.success_threshold}+ ·
                      {plan.assigned_learners.length} learners
                    </p>
                  </div>
                  <div className="admin-plan-actions">
                    <button className="ghost-button" onClick={() => openEditForm(plan)}>Edit</button>
                    <button className="danger-button" onClick={() => handleDelete(plan.plan_id)}>Delete</button>
                  </div>
                </div>
                {plan.description ? <p className="admin-plan-desc">{plan.description}</p> : null}
                <div className="admin-plan-assign">
                  <span className="admin-plan-section-label">Goal: {plan.goal_criteria}</span>
                </div>
                {plan.assigned_learners.length > 0 ? (
                  <div className="admin-plan-learners">
                    <span className="admin-plan-section-label">Learners:</span>
                    {plan.assigned_learners.map((learnerId) => (
                      <span className="skill-tag" key={learnerId}>
                        {learnerId}
                        <button
                          className="tag-remove"
                          onClick={() => handleUnassign(plan.plan_id, learnerId)}
                          title="Remove learner"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                ) : (
                  <div className="admin-plan-learners">
                    <span className="admin-plan-section-label muted">No learners assigned</span>
                  </div>
                )}
                <div className="admin-plan-assign-row">
                  <input
                    type="text"
                    placeholder="Add learners (comma-separated IDs)..."
                    value={assignInput[plan.plan_id] ?? ""}
                    onChange={(e) => setAssignInput((prev) => ({ ...prev, [plan.plan_id]: e.target.value }))}
                  />
                  <button className="primary-button" onClick={() => handleAssign(plan.plan_id)}>Assign</button>
                </div>
                <div className="admin-plan-footer">
                  <small>Created: {formatTimestamp(plan.created_at)}</small>
                  <small>Updated: {formatTimestamp(plan.updated_at)}</small>
                  <small>v{plan.version}</small>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : !showForm ? (
        <section className="panel surface-card">
          <div className="placeholder-block">
            <strong>No active training plans</strong>
            <p>Create a training plan to assign goals to learners and track their achievement.</p>
          </div>
        </section>
      ) : null}

      {pausedPlans.length > 0 ? (
        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="clock" />
              <span>Paused Plans ({pausedPlans.length})</span>
            </div>
          </div>
          <div className="admin-plan-list">
            {pausedPlans.map((plan) => (
              <article className="admin-plan-card muted" key={plan.plan_id}>
                <div className="admin-plan-head">
                  <div>
                    <h3>{plan.title}</h3>
                    <p className="admin-plan-meta">{plan.plan_id} · {plan.assigned_learners.length} learners</p>
                  </div>
                  <button className="ghost-button" onClick={() => openEditForm(plan)}>Edit</button>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}

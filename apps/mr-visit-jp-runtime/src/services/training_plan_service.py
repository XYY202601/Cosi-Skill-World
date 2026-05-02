from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from persistence.interfaces import TrainingPlanStore


TRAINING_PLAN_STATUSES = frozenset({
    "active",
    "paused",
    "completed",
    "archived",
})


class TrainingPlanError(RuntimeError):
    pass


class TrainingPlanNotFoundError(TrainingPlanError):
    pass


@dataclass
class TrainingPlan:
    plan_id: str
    org_id: str
    title: str
    description: str = ""
    owner_id: str = ""
    assigned_learners: list[str] = field(default_factory=list)
    assigned_cohorts: list[str] = field(default_factory=list)
    target_subskills: list[str] = field(default_factory=list)
    required_scenario_ids: list[str] = field(default_factory=list)
    due_date: str | None = None
    goal_criteria: str = "Achieve 4.0+ on all target subskills"
    success_threshold: float = 4.0
    review_cadence: str = "after_each_session"
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "org_id": self.org_id,
            "title": self.title,
            "description": self.description,
            "owner_id": self.owner_id,
            "assigned_learners": list(self.assigned_learners),
            "assigned_cohorts": list(self.assigned_cohorts),
            "target_subskills": list(self.target_subskills),
            "required_scenario_ids": list(self.required_scenario_ids),
            "due_date": self.due_date,
            "goal_criteria": self.goal_criteria,
            "success_threshold": self.success_threshold,
            "review_cadence": self.review_cadence,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrainingPlan:
        return cls(
            plan_id=str(data.get("plan_id", "")),
            org_id=str(data.get("org_id", "")),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            owner_id=str(data.get("owner_id", "")),
            assigned_learners=list(data.get("assigned_learners", [])),
            assigned_cohorts=list(data.get("assigned_cohorts", [])),
            target_subskills=list(data.get("target_subskills", [])),
            required_scenario_ids=list(data.get("required_scenario_ids", [])),
            due_date=data.get("due_date"),
            goal_criteria=str(data.get("goal_criteria", "Achieve 4.0+ on all target subskills")),
            success_threshold=float(data.get("success_threshold", 4.0)),
            review_cadence=str(data.get("review_cadence", "after_each_session")),
            status=str(data.get("status", "active")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            version=int(data.get("version", 1)),
        )


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalize_plan_id(raw_id: str) -> str:
    return raw_id.strip() if isinstance(raw_id, str) else ""


def _validate_plan_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a training plan payload for creation/update."""
    title = str(payload.get("title", "")).strip()
    if not title:
        raise TrainingPlanError("title is required and must not be empty")

    org_id = str(payload.get("org_id", "")).strip()
    if not org_id:
        raise TrainingPlanError("org_id is required and must not be empty")

    status = str(payload.get("status", "active")).strip().lower()
    if status not in TRAINING_PLAN_STATUSES:
        status = "active"

    target_subskills = [
        s.strip() for s in payload.get("target_subskills", [])
        if isinstance(s, str) and s.strip()
    ]
    required_scenario_ids = [
        s.strip() for s in payload.get("required_scenario_ids", [])
        if isinstance(s, str) and s.strip()
    ]
    assigned_learners = [
        s.strip() for s in payload.get("assigned_learners", [])
        if isinstance(s, str) and s.strip()
    ]
    assigned_cohorts = [
        s.strip() for s in payload.get("assigned_cohorts", [])
        if isinstance(s, str) and s.strip()
    ]

    goal_criteria = str(payload.get("goal_criteria", "")).strip()
    if not goal_criteria:
        goal_criteria = f"Achieve {payload.get('success_threshold', 4.0)}+ on all target subskills"

    return {
        "plan_id": _normalize_plan_id(payload.get("plan_id", "")),
        "org_id": org_id,
        "title": title,
        "description": str(payload.get("description", "")).strip(),
        "owner_id": str(payload.get("owner_id", "")).strip(),
        "assigned_learners": assigned_learners,
        "assigned_cohorts": assigned_cohorts,
        "target_subskills": target_subskills,
        "required_scenario_ids": required_scenario_ids,
        "due_date": str(payload.get("due_date", "")).strip() or None,
        "goal_criteria": goal_criteria,
        "success_threshold": float(payload.get("success_threshold", 4.0)),
        "review_cadence": str(payload.get("review_cadence", "after_each_session")).strip(),
        "status": status,
    }


class TrainingPlanService:
    """Service for managing training plans."""

    def __init__(self, store: TrainingPlanStore) -> None:
        self._store = store

    def create_plan(self, payload: dict[str, Any]) -> TrainingPlan:
        now = _utc_now_iso()
        validated = _validate_plan_payload(payload)
        plan_id = validated["plan_id"] or f"plan_{uuid4().hex[:12]}"
        plan = TrainingPlan(
            plan_id=plan_id,
            org_id=validated["org_id"],
            title=validated["title"],
            description=validated["description"],
            owner_id=validated["owner_id"],
            assigned_learners=validated["assigned_learners"],
            assigned_cohorts=validated["assigned_cohorts"],
            target_subskills=validated["target_subskills"],
            required_scenario_ids=validated["required_scenario_ids"],
            due_date=validated["due_date"],
            goal_criteria=validated["goal_criteria"],
            success_threshold=validated["success_threshold"],
            review_cadence=validated["review_cadence"],
            status=validated["status"],
            created_at=now,
            updated_at=now,
            version=1,
        )
        self._store.create(plan.to_dict())
        return plan

    def update_plan(self, plan_id: str, payload: dict[str, Any]) -> TrainingPlan:
        existing = self._store.get(plan_id)
        if existing is None:
            raise TrainingPlanNotFoundError(f"Training plan not found: {plan_id}")

        now = _utc_now_iso()
        validated = _validate_plan_payload(payload)

        plan = TrainingPlan.from_dict(existing)
        plan.title = validated["title"]
        plan.description = validated["description"]
        plan.owner_id = validated["owner_id"]
        plan.assigned_learners = validated["assigned_learners"]
        plan.assigned_cohorts = validated["assigned_cohorts"]
        plan.target_subskills = validated["target_subskills"]
        plan.required_scenario_ids = validated["required_scenario_ids"]
        plan.due_date = validated["due_date"]
        plan.goal_criteria = validated["goal_criteria"]
        plan.success_threshold = validated["success_threshold"]
        plan.review_cadence = validated["review_cadence"]
        plan.status = validated["status"]
        plan.updated_at = now
        plan.version += 1

        self._store.update(plan_id, plan.to_dict())
        return plan

    def get_plan(self, plan_id: str) -> TrainingPlan:
        raw = self._store.get(plan_id)
        if raw is None:
            raise TrainingPlanNotFoundError(f"Training plan not found: {plan_id}")
        return TrainingPlan.from_dict(raw)

    def list_plans(
        self,
        *,
        org_id: str | None = None,
        learner_id: str | None = None,
    ) -> list[TrainingPlan]:
        raw_list = self._store.list_all(org_id=org_id, learner_id=learner_id)
        return [TrainingPlan.from_dict(item) for item in raw_list]

    def delete_plan(self, plan_id: str) -> None:
        existing = self._store.get(plan_id)
        if existing is None:
            raise TrainingPlanNotFoundError(f"Training plan not found: {plan_id}")
        self._store.delete(plan_id)

    def assign_learners(self, plan_id: str, learner_ids: list[str]) -> TrainingPlan:
        plan = self.get_plan(plan_id)
        existing = set(plan.assigned_learners)
        for lid in learner_ids:
            if isinstance(lid, str) and lid.strip():
                existing.add(lid.strip())
        plan.assigned_learners = sorted(existing)
        plan.updated_at = _utc_now_iso()
        plan.version += 1
        self._store.update(plan_id, plan.to_dict())
        return plan

    def unassign_learners(self, plan_id: str, learner_ids: list[str]) -> TrainingPlan:
        plan = self.get_plan(plan_id)
        remove_set = {lid.strip() for lid in learner_ids if isinstance(lid, str)}
        plan.assigned_learners = [lid for lid in plan.assigned_learners if lid not in remove_set]
        plan.updated_at = _utc_now_iso()
        plan.version += 1
        self._store.update(plan_id, plan.to_dict())
        return plan

    def get_active_plans_for_learner(
        self,
        learner_id: str,
        *,
        org_id: str | None = None,
    ) -> list[TrainingPlan]:
        """Get active training plans assigned to a specific learner."""
        all_plans = self.list_plans(org_id=org_id)
        return [
            plan for plan in all_plans
            if plan.status == "active"
            and learner_id in plan.assigned_learners
        ]

    def maybe_complete_plan(self, plan_id: str, achievement: dict[str, Any]) -> None:
        """Auto-transition plan status to 'completed' when all targets achieved."""
        if achievement.get("status") != "achieved":
            return
        try:
            plan = self.get_plan(plan_id)
        except TrainingPlanNotFoundError:
            return
        if plan.status == "active":
            plan.status = "completed"
            plan.updated_at = _utc_now_iso()
            plan.version += 1
            self._store.update(plan_id, plan.to_dict())

    def evaluate_plan_achievement(
        self,
        plan: TrainingPlan,
        *,
        review: dict[str, Any],
    ) -> dict[str, Any]:
        """Evaluate a training plan's goal achievement against a review.

        Returns an achievement dict compatible with the existing teaching plan
        achievement structure so it can be merged into the continuity channel.
        """
        review_subskills = review.get("subskills", {})
        if not isinstance(review_subskills, dict):
            return {
                "status": "no_plan",
                "achieved_count": 0,
                "total_count": 0,
                "threshold": plan.success_threshold,
            }

        target_subskills = plan.target_subskills
        if not target_subskills:
            return {
                "status": "no_plan",
                "achieved_count": 0,
                "total_count": 0,
                "threshold": plan.success_threshold,
            }

        achieved_count = 0
        total_count = len(target_subskills)
        threshold = plan.success_threshold

        for subskill_id in target_subskills:
            payload = review_subskills.get(subskill_id, {})
            if isinstance(payload, dict):
                score = float(payload.get("score", 0.0))
                if score >= threshold:
                    achieved_count += 1

        if achieved_count >= total_count:
            status = "achieved"
        elif achieved_count > 0:
            status = "partially_achieved"
        else:
            status = "not_achieved"

        return {
            "status": status,
            "achieved_count": achieved_count,
            "total_count": total_count,
            "threshold": threshold,
        }

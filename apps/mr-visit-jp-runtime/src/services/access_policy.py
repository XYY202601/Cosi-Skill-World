"""
Access policy and sharing grants for learner data.

Defines artifact-level permissions per role and supports explicit sharing
grants for controlled cross-learner and cross-role access.

Two layers:
1. Static role-based access: what each role can read by default.
2. Dynamic sharing grants: explicit opt-in sharing for specific artifact types.

Artifact types defined by the K3 spec:
  aggregate_metrics   — team-level aggregate scores, completion rates
  session_metadata    — scenario id, status, timestamp, turn count
  scores_diagnosis    — subskill scores, overall band, diagnosis evidence
  compliance_flags    — compliance severity, rule violations, positive handling
  coach_feedback      — next actions, teaching plan, coaching advice
  transcript_text     — raw turn-by-turn conversation
  review_corrections  — human-annotated review corrections
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ─── Artifact access levels ────────────────────────────────────────────────

# Access level per role per artifact type.
# Levels: "none" (no access), "own" (own data only), "team" (assigned org),
#         "org" (full org), "blocked" (explicitly denied even for org).
ROLE_ARTIFACT_ACCESS: dict[str, dict[str, str]] = {
    "learner": {
        "aggregate_metrics": "none",
        "session_metadata": "own",
        "scores_diagnosis": "own",
        "compliance_flags": "own",
        "coach_feedback": "own",
        "transcript_text": "own",
        "review_corrections": "own",
    },
    "supervisor": {
        "aggregate_metrics": "team",
        "session_metadata": "team",
        "scores_diagnosis": "team",
        "compliance_flags": "team",
        "coach_feedback": "team",
        "transcript_text": "blocked",
        "review_corrections": "blocked",
    },
    "organization_admin": {
        "aggregate_metrics": "org",
        "session_metadata": "org",
        "scores_diagnosis": "org",
        "compliance_flags": "org",
        "coach_feedback": "org",
        "transcript_text": "org",
        "review_corrections": "org",
    },
    "content_admin": {
        "aggregate_metrics": "none",
        "session_metadata": "none",
        "scores_diagnosis": "none",
        "compliance_flags": "none",
        "coach_feedback": "none",
        "transcript_text": "none",
        "review_corrections": "none",
    },
    "platform_admin": {
        "aggregate_metrics": "org",
        "session_metadata": "org",
        "scores_diagnosis": "org",
        "compliance_flags": "org",
        "coach_feedback": "org",
        "transcript_text": "org",
        "review_corrections": "org",
    },
}

ALL_ARTIFACT_TYPES = frozenset(ROLE_ARTIFACT_ACCESS["learner"].keys())


# ─── Sharing grants ─────────────────────────────────────────────────────────

@dataclass
class SharingGrant:
    """Explicit permission for a grantee to access specific artifacts.

    A learner can grant a supervisor access to their transcript/feedback.
    An organization_admin can grant org-wide access to specific artifacts.
    """

    grant_id: str
    granter_id: str             # learner or admin who granted access
    granter_org_id: str         # org context for the grant
    grantee_role: str           # "supervisor" | "organization_admin"
    grantee_scope: str          # "user:<id>" | "cohort:<id>" | "org:<id>"
    artifact_types: list[str]   # subset of ALL_ARTIFACT_TYPES
    reason: str = ""            # optional explanation (e.g. "peer review", "audit")
    expires_at: str | None = None
    created_at: str = ""

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(self.expires_at)
            return expiry < datetime.now(tz=timezone.utc)
        except (ValueError, TypeError):
            return False

    def covers_artifact(self, artifact_type: str) -> bool:
        return artifact_type in self.artifact_types


# ─── Grant store interface ─────────────────────────────────────────────────

@runtime_checkable
class SharingGrantStore(Protocol):
    def create_grant(self, grant: SharingGrant) -> None: ...
    def get_grants_for_grantee(
        self, *, grantee_role: str, grantee_scope: str
    ) -> list[SharingGrant]: ...
    def get_grants_by_granter(self, granter_id: str) -> list[SharingGrant]: ...
    def revoke_grant(self, grant_id: str) -> None: ...


# ─── Access decision ───────────────────────────────────────────────────────

@dataclass
class AccessDecision:
    """Result of an access policy check."""

    allowed: bool
    reason: str = ""
    effective_level: str = "none"  # "none" | "own" | "team" | "org" | "blocked"
    grant_id: str | None = None    # set if a sharing grant was used


def _normalize_role(role: str | None) -> str:
    if not isinstance(role, str):
        return "learner"
    normalized = role.strip().lower()
    if normalized in ROLE_ARTIFACT_ACCESS:
        return normalized
    return "learner"


def resolve_artifact_access(
    role: str | None,
    artifact_type: str,
) -> AccessDecision:
    """Check role-based default access to an artifact type.

    Does NOT consult sharing grants — use ``check_artifact_access`` for that.
    """
    normalized_role = _normalize_role(role)
    role_rules = ROLE_ARTIFACT_ACCESS.get(normalized_role, {})
    level = role_rules.get(artifact_type, "none")

    if level == "none":
        return AccessDecision(
            allowed=False,
            reason=f"Role '{normalized_role}' has no access to artifact '{artifact_type}'.",
            effective_level="none",
        )
    if level == "blocked":
        return AccessDecision(
            allowed=False,
            reason=f"Role '{normalized_role}' is explicitly blocked from artifact '{artifact_type}'.",
            effective_level="blocked",
        )
    # "own", "team", "org" are all allowed — scope enforcement happens at caller
    return AccessDecision(
        allowed=True,
        reason=f"Role '{normalized_role}' has '{level}' access to '{artifact_type}'.",
        effective_level=level,
    )


def check_artifact_access(
    role: str | None,
    artifact_type: str,
    *,
    is_own_data: bool = False,
    is_same_org: bool = False,
    grants: list[SharingGrant] | None = None,
) -> AccessDecision:
    """Full access check combining role-based policy and sharing grants.

    Args:
        role: The viewer's role (e.g. "learner", "supervisor").
        artifact_type: One of ALL_ARTIFACT_TYPES.
        is_own_data: True if the target data belongs to the requesting user.
        is_same_org: True if the target data is in the same org.
        grants: Optional sharing grants to consider.

    Returns:
        AccessDecision with ``allowed``, ``reason``, ``effective_level``.
    """
    normalized_role = _normalize_role(role)
    role_rules = ROLE_ARTIFACT_ACCESS.get(normalized_role, {})
    level = role_rules.get(artifact_type, "none")

    # Blocked roles are blocked regardless of grants
    if level == "blocked":
        return AccessDecision(
            allowed=False,
            reason=f"Role '{normalized_role}' is explicitly blocked from '{artifact_type}'.",
            effective_level="blocked",
        )

    # Check scope requirements
    if level == "own" and not is_own_data:
        # Try sharing grants
        if grants:
            matching = [
                g for g in grants
                if g.covers_artifact(artifact_type) and not g.is_expired()
            ]
            if matching:
                return AccessDecision(
                    allowed=True,
                    reason=f"Grant ({matching[0].grant_id}) allows '{artifact_type}' access.",
                    effective_level="own",
                    grant_id=matching[0].grant_id,
                )
        return AccessDecision(
            allowed=False,
            reason=f"Role '{normalized_role}' has only 'own' access to '{artifact_type}', "
                   f"and target is not owned by the requester.",
            effective_level="own",
        )

    if level == "team" and not is_same_org:
        return AccessDecision(
            allowed=False,
            reason=f"Role '{normalized_role}' has 'team' access to '{artifact_type}', "
                   f"but target is outside the viewer's org scope.",
            effective_level="team",
        )

    if level == "org" and not is_same_org:
        return AccessDecision(
            allowed=False,
            reason=f"Role '{normalized_role}' has 'org' access to '{artifact_type}', "
                   f"but target is outside the viewer's org scope.",
            effective_level="org",
        )

    if level == "none":
        return AccessDecision(
            allowed=False,
            reason=f"Role '{normalized_role}' has no access to '{artifact_type}'.",
            effective_level="none",
        )

    return AccessDecision(
        allowed=True,
        reason=f"Role '{normalized_role}' has '{level}' access to '{artifact_type}'.",
        effective_level=level,
    )


def grant_learner_to_supervisor_access(
    learner_id: str,
    org_id: str,
    supervisor_scope: str,       # "user:<supervisor_id>" | "org:<org_id>"
    artifact_types: list[str] | None = None,
    reason: str = "",
    expires_at: str | None = None,
) -> SharingGrant:
    """Create a sharing grant for a learner to share data with a supervisor."""
    return SharingGrant(
        grant_id=f"grant_{uuid4().hex[:12]}",
        granter_id=learner_id,
        granter_org_id=org_id,
        grantee_role="supervisor",
        grantee_scope=supervisor_scope,
        artifact_types=artifact_types or list(ALL_ARTIFACT_TYPES),
        reason=reason,
        expires_at=expires_at,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )


def grant_admin_org_access(
    admin_id: str,
    org_id: str,
    artifact_types: list[str] | None = None,
    reason: str = "",
    expires_at: str | None = None,
) -> SharingGrant:
    """Create an org-wide grant (for organization_admin use)."""
    return SharingGrant(
        grant_id=f"grant_{uuid4().hex[:12]}",
        granter_id=admin_id,
        granter_org_id=org_id,
        grantee_role="organization_admin",
        grantee_scope=f"org:{org_id}",
        artifact_types=artifact_types or list(ALL_ARTIFACT_TYPES),
        reason=reason,
        expires_at=expires_at,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )

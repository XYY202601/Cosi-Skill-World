"""
Audit logging for sensitive access paths.

Records structured audit events for:
- Review reads (who viewed whose review)
- Transcript reads (who accessed raw session transcripts)
- Admin operations (training plan CRUD, evaluation gate access)
- Plan assignments / unassignments
- Organization report reads

Each audit event includes: actor (auth_user), action, target type,
target ID, org ID, timestamp, result (granted/denied), and detail.

Audit logs are written at INFO level with event=audit.* so they can be
routed to a separate audit sink in production deployments.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import Request

AUDIT_LOGGER = logging.getLogger("mr_visit_jp_runtime.audit")


def _normalize_string(value: Any) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return ""


def _normalize_optional_string(value: Any) -> str | None:
    normalized = _normalize_string(value)
    return normalized or None


def _extract_auth_user(request: Request) -> str | None:
    """Extract the authenticated user from request headers or state."""
    return _normalize_optional_string(request.headers.get("x-auth-user"))


def _extract_org_id(request: Request) -> str | None:
    return _normalize_optional_string(request.headers.get("x-org-id"))


def _extract_viewer_role(request: Request) -> str | None:
    role = _normalize_optional_string(request.headers.get("x-viewer-role"))
    return role.lower() if role else None


def log_sensitive_access(
    request: Request,
    *,
    action: str,
    target_type: str,
    target_id: str | None = None,
    learner_id: str | None = None,
    result: str = "granted",
    detail: str | None = None,
) -> None:
    """Log a structured audit event for a sensitive access path.

    Args:
        request: The FastAPI request object (used to extract actor/org/role).
        action: Short action name, e.g. 'review.read', 'transcript.read',
            'plan.create', 'plan.assign', 'report.read'.
        target_type: Type of resource being accessed, e.g. 'session', 'plan',
            'learner_progress', 'organization_report', 'evaluation_gate'.
        target_id: ID of the specific resource (session_id, plan_id, etc.).
        learner_id: The learner whose data is being accessed (if applicable).
        result: 'granted' or 'denied'.
        detail: Free-text explanation or context.
    """
    actor = _extract_auth_user(request)
    org_id = _extract_org_id(request)
    viewer_role = _extract_viewer_role(request)
    timestamp = datetime.now(tz=timezone.utc).isoformat()

    payload: dict[str, Any] = {
        "event": f"audit.{action}",
        "actor": actor or "anonymous",
        "auth_role": viewer_role or "unknown",
        "org_id": org_id or "none",
        "target_type": target_type,
        "target_id": target_id or "unknown",
        "result": result,
        "timestamp": timestamp,
    }

    if learner_id is not None:
        payload["learner_id"] = learner_id
    if detail is not None:
        payload["detail"] = detail

    # Include trace context if available for correlation
    try:
        from runtime_observability import get_request_log_context

        trace_context = get_request_log_context(request)
        payload["request_id"] = trace_context.request_id
        payload["trace_id"] = trace_context.trace_id
    except (RuntimeError, ImportError):
        pass

    AUDIT_LOGGER.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))

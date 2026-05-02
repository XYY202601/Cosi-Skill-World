from __future__ import annotations

import os
from time import perf_counter
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from hermes_observability import (
    apply_response_trace_headers,
    bind_proxy_headers,
    bind_request_metadata,
    build_forward_headers,
    emit_request_log,
    initialize_request_log_context,
)
from org_skill_store import INSTALL_STATES, OrgSkillStore, OrgSkillStoreError
from pydantic import BaseModel, Field

from runtime_proxy import RuntimeProxyError, RuntimeProxyResult, get_deploy_env, proxy_runtime_request, validate_runtime_env
from skill_registry import (
    SkillManifest,
    SkillRegistryError,
    get_skill_registry,
    resolve_runtime_api_base,
)

app = FastAPI(title="hermes-orchestrator", version="0.1.0")


@app.on_event("startup")
async def _validate_deploy_env_on_startup() -> None:
    try:
        validate_runtime_env()
    except RuntimeError as exc:
        import logging as _logging

        _logging.getLogger("hermes-orchestrator.startup").error(str(exc))
        raise SystemExit(1) from exc


@app.middleware("http")
async def hermes_request_observability(request: Request, call_next):
    initialize_request_log_context(request, service_name="hermes-orchestrator")
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (perf_counter() - started_at) * 1000
        emit_request_log(request, status_code=500, duration_ms=duration_ms, error=exc)
        raise

    apply_response_trace_headers(response, request)
    duration_ms = (perf_counter() - started_at) * 1000
    emit_request_log(request, status_code=response.status_code, duration_ms=duration_ms)
    return response


class StartSessionRequest(BaseModel):
    scenario_id: str
    learner_id: str


class SendTurnRequest(BaseModel):
    message: str = Field(min_length=1)


class MarketplaceInstallRequest(BaseModel):
    skill_id: str = Field(min_length=1)
    version: str = ""
    installed_by: str = ""


class MarketplaceStateRequest(BaseModel):
    state: str = Field(min_length=1)
    reason: str = ""


# ── OrgSkillStore singleton ──────────────────────────────────────────
_org_skill_store: OrgSkillStore | None = None


def _get_org_skill_store() -> OrgSkillStore:
    global _org_skill_store
    if _org_skill_store is None:
        _org_skill_store = OrgSkillStore()
    return _org_skill_store


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def _should_auto_install_local_skill(org_id: str) -> bool:
    if get_deploy_env() != "development":
        return False
    if org_id.strip().lower() != "local":
        return False
    return _env_flag("HERMES_LOCAL_AUTO_INSTALL_SKILLS", True)


def _ensure_local_skill_installed(store: OrgSkillStore, org_id: str, skill_id: str) -> bool:
    if not _should_auto_install_local_skill(org_id):
        return False
    try:
        store.install_skill(
            org_id,
            skill_id,
            version="",
            installed_by="hermes:auto-install",
        )
    except OrgSkillStoreError:
        return False
    return True


def _extract_org_id(request: Request) -> str | None:
    """Extract org id from request headers (X-Org-ID or x-org-id)."""
    raw = request.headers.get("X-Org-ID") or request.headers.get("x-org-id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _check_skill_installation(
    request: Request, skill_id: str, action_id: str,
) -> None:
    """Check whether the skill is installed for the caller's org.

    Only enforced for session-start actions when X-Org-ID is present.
    Skips check for unscoped routes using default skill in demo mode
    (no X-Org-ID header).
    """
    org_id = _extract_org_id(request)
    if org_id is None:
        return  # demo mode or auth-disabled
    if action_id not in ("start_session",):
        return  # only enforce on session start
    store = _get_org_skill_store()
    if not store.is_skill_available_for_learner(org_id, skill_id):
        auto_installed = _ensure_local_skill_installed(store, org_id, skill_id)
        if auto_installed and store.is_skill_available_for_learner(org_id, skill_id):
            return
        raise HTTPException(
            status_code=403,
            detail=(
                f"Skill `{skill_id}` is not installed for organization "
                f"`{org_id}`. Contact your organization administrator to "
                f"install this skill."
            ),
        )


def _registry():
    return get_skill_registry()


def _resolve_skill(skill_id: str | None = None) -> SkillManifest:
    try:
        if skill_id is None:
            return _registry().default_skill()
        return _registry().require(skill_id)
    except SkillRegistryError as exc:
        status_code = 404 if skill_id is not None else 500
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


def _skill_list_payload() -> dict[str, Any]:
    registry = _registry()
    summaries = registry.list_summaries()
    default_skill_id = None
    try:
        default_skill_id = registry.default_skill().id
    except SkillRegistryError:
        default_skill_id = None
    return {
        "skills": registry.list_skill_ids(),
        "default_skill_id": default_skill_id,
        "items": summaries,
    }


def _default_skill_runtime_api_base() -> str | None:
    try:
        skill = _registry().default_skill()
    except SkillRegistryError:
        return None
    return resolve_runtime_api_base(skill.runtime)


def _hermes_diagnostics_payload() -> dict[str, Any]:
    payload = _skill_list_payload()
    runtime_api_base = _default_skill_runtime_api_base()
    return {
        "status": "ok",
        "service_name": "hermes-orchestrator",
        "deploy_env": get_deploy_env(),
        "default_skill_id": payload["default_skill_id"],
        "skill_count": len(payload["skills"]),
        "skills": payload["items"],
        "runtime_api_base": runtime_api_base,
        "health_targets": {
            "runtime": (
                f"{runtime_api_base}/healthz"
                if isinstance(runtime_api_base, str) and runtime_api_base
                else None
            ),
        },
        "forward_trace_headers": [
            "x-request-id",
            "x-trace-id",
            "x-session-id",
            "x-turn-id",
        ],
    }


def _json_response(result: RuntimeProxyResult) -> JSONResponse:
    return JSONResponse(content=result.payload, status_code=result.status)


def _payload_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    return {}


def _string_field(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _bind_proxy_result_metadata(request: Request, result: RuntimeProxyResult) -> None:
    bind_proxy_headers(request, result.headers)
    payload = _payload_dict(result.payload)
    bind_request_metadata(
        request,
        session_id=_string_field(payload, "session_id"),
        learner_id=_string_field(payload, "learner_id"),
        turn_id=result.headers.get("x-turn-id"),
    )
    experiment_context = payload.get("experiment_context")
    if isinstance(experiment_context, dict):
        bind_request_metadata(
            request,
            prompt_profile=_string_field(experiment_context, "profile_id"),
            experiment_id=_string_field(experiment_context, "experiment_id"),
        )


async def _proxy_action(
    request: Request,
    action_id: str,
    *,
    skill_id: str | None = None,
    path_values: dict[str, str] | None = None,
    json_body: Any | None = None,
) -> JSONResponse:
    learner_id = None
    if isinstance(json_body, dict):
        learner_id = json_body.get("learner_id")
    if learner_id is None and path_values is not None:
        learner_id = path_values.get("learner_id")
    session_id = path_values.get("session_id") if path_values is not None else None
    bind_request_metadata(
        request,
        action_id=action_id,
        session_id=session_id,
        learner_id=learner_id if isinstance(learner_id, str) else None,
    )
    skill = _resolve_skill(skill_id)
    bind_request_metadata(request, domain_id=skill.id)
    _check_skill_installation(request, skill.id, action_id)
    try:
        action = skill.action(action_id)
        runtime_path = action.build_runtime_path(
            base_path=skill.runtime.base_path,
            path_values=path_values,
        )
        result = await proxy_runtime_request(
            path=runtime_path,
            method=action.method,
            json_body=json_body,
            runtime_api_base=resolve_runtime_api_base(skill.runtime),
            headers=build_forward_headers(request),
        )
    except SkillRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeProxyError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _bind_proxy_result_metadata(request, result)
    return _json_response(result)


@app.get("/healthz")
def healthz(request: Request) -> dict[str, Any]:
    payload = _skill_list_payload()
    default_skill = None
    try:
        default_skill = _registry().default_skill()
    except SkillRegistryError:
        default_skill = None
    bind_request_metadata(
        request,
        action_id="healthz",
        domain_id=default_skill.id if default_skill is not None else None,
    )
    return {
        "status": "ok",
        "skills": payload["skills"],
        "default_skill_id": payload["default_skill_id"],
        "skill_count": len(payload["skills"]),
        "runtime_api_base": _default_skill_runtime_api_base(),
    }


@app.get("/_local/diagnostics")
def local_diagnostics(request: Request) -> dict[str, Any]:
    diagnostics = _hermes_diagnostics_payload()
    bind_request_metadata(
        request,
        action_id="local_diagnostics",
        domain_id=(
            str(diagnostics["default_skill_id"]).strip()
            if diagnostics.get("default_skill_id") is not None
            else None
        ),
    )
    return diagnostics


@app.get("/v1/skills")
def list_skills(request: Request) -> dict[str, Any]:
    bind_request_metadata(request, action_id="list_skills")
    return _skill_list_payload()


@app.get("/v1/scenarios")
async def list_scenarios(request: Request) -> JSONResponse:
    return await _proxy_action(request, "list_scenarios")


@app.get("/v1/evaluation-gates")
async def get_evaluation_gates(request: Request) -> JSONResponse:
    return await _proxy_action(request, "get_evaluation_gates")


@app.get("/v1/skills/{skill_id}/scenarios")
async def list_skill_scenarios(request: Request, skill_id: str) -> JSONResponse:
    return await _proxy_action(request, "list_scenarios", skill_id=skill_id)


@app.get("/v1/skills/{skill_id}/evaluation-gates")
async def get_skill_evaluation_gates(request: Request, skill_id: str) -> JSONResponse:
    return await _proxy_action(request, "get_evaluation_gates", skill_id=skill_id)


@app.post("/v1/sessions/start")
async def start_session(request: Request, payload: StartSessionRequest) -> JSONResponse:
    return await _proxy_action(
        request,
        "start_session",
        json_body=payload.model_dump(),
    )


@app.post("/v1/skills/{skill_id}/sessions/start")
async def start_skill_session(
    request: Request,
    skill_id: str,
    payload: StartSessionRequest,
) -> JSONResponse:
    return await _proxy_action(
        request,
        "start_session",
        skill_id=skill_id,
        json_body=payload.model_dump(),
    )


@app.get("/v1/sessions/{session_id}")
async def get_session(request: Request, session_id: str) -> JSONResponse:
    return await _proxy_action(
        request,
        "get_session",
        path_values={"session_id": session_id},
    )


@app.get("/v1/skills/{skill_id}/sessions/{session_id}")
async def get_skill_session(
    request: Request,
    skill_id: str,
    session_id: str,
) -> JSONResponse:
    return await _proxy_action(
        request,
        "get_session",
        skill_id=skill_id,
        path_values={"session_id": session_id},
    )


@app.post("/v1/sessions/{session_id}/turn")
async def send_turn(
    request: Request,
    session_id: str,
    payload: SendTurnRequest,
) -> JSONResponse:
    return await _proxy_action(
        request,
        "send_turn",
        path_values={"session_id": session_id},
        json_body=payload.model_dump(),
    )


@app.post("/v1/skills/{skill_id}/sessions/{session_id}/turn")
async def send_skill_turn(
    request: Request,
    skill_id: str,
    session_id: str,
    payload: SendTurnRequest,
) -> JSONResponse:
    return await _proxy_action(
        request,
        "send_turn",
        skill_id=skill_id,
        path_values={"session_id": session_id},
        json_body=payload.model_dump(),
    )


@app.post("/v1/sessions/{session_id}/finish")
async def finish_session(request: Request, session_id: str) -> JSONResponse:
    return await _proxy_action(
        request,
        "finish_session",
        path_values={"session_id": session_id},
    )


@app.post("/v1/skills/{skill_id}/sessions/{session_id}/finish")
async def finish_skill_session(
    request: Request,
    skill_id: str,
    session_id: str,
) -> JSONResponse:
    return await _proxy_action(
        request,
        "finish_session",
        skill_id=skill_id,
        path_values={"session_id": session_id},
    )


@app.get("/v1/sessions/{session_id}/review")
async def get_review(request: Request, session_id: str) -> JSONResponse:
    return await _proxy_action(
        request,
        "get_review",
        path_values={"session_id": session_id},
    )


@app.get("/v1/skills/{skill_id}/sessions/{session_id}/review")
async def get_skill_review(
    request: Request,
    skill_id: str,
    session_id: str,
) -> JSONResponse:
    return await _proxy_action(
        request,
        "get_review",
        skill_id=skill_id,
        path_values={"session_id": session_id},
    )


@app.get("/v1/sessions/{session_id}/events")
async def get_session_events(request: Request, session_id: str) -> JSONResponse:
    return await _proxy_action(
        request,
        "get_session_events",
        path_values={"session_id": session_id},
    )


@app.get("/v1/skills/{skill_id}/sessions/{session_id}/events")
async def get_skill_session_events(
    request: Request,
    skill_id: str,
    session_id: str,
) -> JSONResponse:
    return await _proxy_action(
        request,
        "get_session_events",
        skill_id=skill_id,
        path_values={"session_id": session_id},
    )


@app.get("/v1/learners/{learner_id}/progress")
async def get_progress_snapshot(request: Request, learner_id: str) -> JSONResponse:
    return await _proxy_action(
        request,
        "get_progress_snapshot",
        path_values={"learner_id": learner_id},
    )


@app.get("/v1/skills/{skill_id}/learners/{learner_id}/progress")
async def get_skill_progress_snapshot(
    request: Request,
    skill_id: str,
    learner_id: str,
) -> JSONResponse:
    return await _proxy_action(
        request,
        "get_progress_snapshot",
        skill_id=skill_id,
        path_values={"learner_id": learner_id},
    )


@app.get("/v1/organizations/{organization_id}/reports")
async def get_organization_reports(
    request: Request,
    organization_id: str,
) -> JSONResponse:
    return await _proxy_action(
        request,
        "get_organization_reports",
        path_values={"organization_id": organization_id},
    )


@app.get("/v1/skills/{skill_id}/organizations/{organization_id}/reports")
async def get_skill_organization_reports(
    request: Request,
    skill_id: str,
    organization_id: str,
) -> JSONResponse:
    return await _proxy_action(
        request,
        "get_organization_reports",
        skill_id=skill_id,
        path_values={"organization_id": organization_id},
    )


# ── Marketplace / Org Skill Installation API ─────────────────────────


@app.get("/v1/marketplace")
def list_marketplace_skills(request: Request) -> dict[str, Any]:
    """List all available skills with their marketplace metadata.

    Includes installation state for the requesting org if X-Org-ID is present.
    """
    bind_request_metadata(request, action_id="list_marketplace_skills")
    registry = _registry()
    skill_summaries = registry.list_summaries()
    org_id = _extract_org_id(request)

    items: list[dict[str, Any]] = []
    for summary in skill_summaries:
        skill_id = summary["id"]
        item = dict(summary)
        if org_id:
            store = _get_org_skill_store()
            inst = store.get_installation(org_id, skill_id)
            item["installation"] = inst or {"state": "available"}
        else:
            item["installation"] = {"state": "available"}
        items.append(item)

    return {
        "skills": registry.list_skill_ids(),
        "default_skill_id": (
            registry.default_skill().id
            if _has_default_skill(registry) else None
        ),
        "items": items,
    }


def _has_default_skill(registry) -> bool:
    try:
        registry.default_skill()
        return True
    except SkillRegistryError:
        return False


@app.get("/v1/marketplace/org/{org_id}/skills")
def list_org_skills(
    request: Request,
    org_id: str,
    state: str | None = None,
) -> dict[str, Any]:
    """List skill installation records for an org, optionally filtered by state."""
    bind_request_metadata(request, action_id="list_org_skills")
    store = _get_org_skill_store()
    records = store.list_org_skills(org_id, state_filter=state)
    return {
        "org_id": org_id,
        "skills": records,
        "count": len(records),
    }


@app.post("/v1/marketplace/org/{org_id}/install", status_code=201)
def install_org_skill(
    request: Request,
    org_id: str,
    payload: MarketplaceInstallRequest,
) -> dict[str, Any]:
    """Install a skill for an organization."""
    bind_request_metadata(request, action_id="install_org_skill")
    store = _get_org_skill_store()
    try:
        record = store.install_skill(
            org_id,
            payload.skill_id,
            version=payload.version,
            installed_by=payload.installed_by,
        )
    except OrgSkillStoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return record


@app.post("/v1/marketplace/org/{org_id}/skills/{skill_id}/state")
def set_org_skill_state(
    request: Request,
    org_id: str,
    skill_id: str,
    payload: MarketplaceStateRequest,
) -> dict[str, Any]:
    """Change the installation state of a skill for an org."""
    bind_request_metadata(request, action_id="set_org_skill_state")
    store = _get_org_skill_store()
    try:
        record = store.set_state(
            org_id, skill_id, payload.state,
            reason=payload.reason,
        )
    except OrgSkillStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return record


@app.delete("/v1/marketplace/org/{org_id}/skills/{skill_id}", status_code=204)
def remove_org_skill(
    request: Request,
    org_id: str,
    skill_id: str,
) -> None:
    """Remove a skill from an org's installation state."""
    bind_request_metadata(request, action_id="remove_org_skill")
    store = _get_org_skill_store()
    store.remove_skill(org_id, skill_id)


# ── Cross-skill Dashboard ────────────────────────────────────────────────


@app.get("/v1/marketplace/org/{org_id}/dashboard")
async def get_org_dashboard(
    request: Request,
    org_id: str,
    learner_id: str | None = None,
) -> dict[str, Any]:
    """Cross-skill dashboard: progress summaries across all installed skills."""
    bind_request_metadata(request, action_id="get_org_dashboard")
    store = _get_org_skill_store()
    registry = _registry()
    records = store.list_org_skills(org_id)

    skills_summary: list[dict[str, Any]] = []
    for skill_id, record in records.items():
        if record.get("state") != "installed":
            continue
        skill = registry.get(skill_id)
        if skill is None:
            continue

        summary_entry: dict[str, Any] = {
            "skill_id": skill_id,
            "skill_name": skill.marketplace.title or skill.name,
            "state": record["state"],
            "installed_version": record.get("installed_version", ""),
            "marketplace": skill.marketplace.to_dict() if skill.marketplace.title else None,
        }

        if learner_id:
            try:
                action = skill.action("get_progress_snapshot")
                runtime_path = action.build_runtime_path(
                    base_path=skill.runtime.base_path,
                    path_values={"learner_id": learner_id},
                )
                result = await proxy_runtime_request(
                    path=runtime_path,
                    method="GET",
                    runtime_api_base=resolve_runtime_api_base(skill.runtime),
                    headers=build_forward_headers(request),
                )
                if result.status == 200 and isinstance(result.payload, dict):
                    progress = result.payload
                    summary_entry["progress"] = {
                        "total_sessions": progress.get("total_sessions", 0),
                        "finalized_sessions": progress.get("finalized_sessions", 0),
                        "overall_band": progress.get("overall_band"),
                        "overall_score": progress.get("overall_score"),
                        "compliance_risk_count": progress.get("compliance_risk_session_count", 0),
                        "has_progress": True,
                    }
                else:
                    summary_entry["progress"] = {"has_progress": False}
            except Exception:
                summary_entry["progress"] = {"has_progress": False}
        else:
            summary_entry["progress"] = {"has_progress": False}

        skills_summary.append(summary_entry)

    return {
        "org_id": org_id,
        "learner_id": learner_id,
        "installed_skill_count": len(skills_summary),
        "skills": skills_summary,
    }

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

from fastapi import Request, Response


LOGGER = logging.getLogger("mr_visit_jp_runtime.observability")
REQUEST_CONTEXT_STATE_KEY = "cosi_request_log_context"
TRACE_RESPONSE_HEADERS = (
    "x-request-id",
    "x-trace-id",
    "x-session-id",
    "x-turn-id",
    "x-service-name",
)
LEARNER_PROGRESS_PATH_RE = re.compile(r"(/learners/)[^/]+(/progress)")


def _normalize_string(value: Any) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return ""


def _normalize_optional_string(value: Any) -> str | None:
    normalized = _normalize_string(value)
    return normalized or None


def _sanitize_path(path: str) -> str:
    normalized = _normalize_string(path)
    if not normalized:
        return ""
    return LEARNER_PROGRESS_PATH_RE.sub(r"\1{learner_id}\2", normalized)


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _hash_identifier(value: str | None) -> str | None:
    normalized = _normalize_string(value)
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def _extract_value(source: Any, field: str) -> Any:
    if isinstance(source, dict):
        return source.get(field)
    return getattr(source, field, None)


def _sanitize_error(error: Any) -> str | None:
    if error is None:
        return None
    if isinstance(error, (str, int, float, bool)):
        normalized = _normalize_string(str(error))
    else:
        normalized = _normalize_string(type(error).__name__)
    if not normalized:
        return None
    return normalized[:160]


def _log_level_for_status(status_code: int) -> int:
    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO


@dataclass
class RequestLogContext:
    service_name: str
    request_id: str
    trace_id: str
    method: str
    path: str
    domain_id: str | None = None
    action_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    learner_hash: str | None = None
    prompt_profile: str | None = None
    experiment_id: str | None = None
    upstream_service_name: str | None = None


def initialize_request_log_context(
    request: Request,
    *,
    service_name: str,
    domain_id: str | None = None,
) -> RequestLogContext:
    context = RequestLogContext(
        service_name=service_name,
        request_id=_normalize_string(request.headers.get("x-request-id")) or _generate_id("req"),
        trace_id=_normalize_string(request.headers.get("x-trace-id")) or _generate_id("trace"),
        method=request.method,
        path=_sanitize_path(request.url.path),
        domain_id=_normalize_optional_string(domain_id),
    )
    setattr(request.state, REQUEST_CONTEXT_STATE_KEY, context)
    return context


def get_request_log_context(request: Request) -> RequestLogContext:
    context = getattr(request.state, REQUEST_CONTEXT_STATE_KEY, None)
    if context is None:
        raise RuntimeError("Request log context has not been initialized.")
    return context


def bind_request_metadata(
    request: Request,
    *,
    domain_id: str | None = None,
    action_id: str | None = None,
    session_id: str | None = None,
    turn_id: str | None = None,
    learner_id: str | None = None,
    prompt_profile: str | None = None,
    experiment_id: str | None = None,
    trace_id: str | None = None,
) -> RequestLogContext:
    context = get_request_log_context(request)
    if domain_id is not None:
        context.domain_id = _normalize_optional_string(domain_id)
    if action_id is not None:
        context.action_id = _normalize_optional_string(action_id)
    if session_id is not None:
        context.session_id = _normalize_optional_string(session_id)
    if turn_id is not None:
        context.turn_id = _normalize_optional_string(turn_id)
    if learner_id is not None:
        context.learner_hash = _hash_identifier(learner_id)
    if prompt_profile is not None:
        context.prompt_profile = _normalize_optional_string(prompt_profile)
    if experiment_id is not None:
        context.experiment_id = _normalize_optional_string(experiment_id)
    if trace_id is not None:
        normalized_trace_id = _normalize_optional_string(trace_id)
        if normalized_trace_id is not None:
            context.trace_id = normalized_trace_id
    return context


def bind_session_context(request: Request, session_context: Any) -> RequestLogContext:
    return bind_request_metadata(
        request,
        domain_id=_extract_value(session_context, "skill_id"),
        session_id=_extract_value(session_context, "session_id"),
        turn_id=_extract_value(session_context, "turn_id"),
        learner_id=_extract_value(session_context, "learner_id"),
        prompt_profile=_extract_value(session_context, "prompt_profile"),
        experiment_id=_extract_value(session_context, "experiment_id"),
        trace_id=_extract_value(session_context, "trace_id"),
    )


def build_forward_headers(request: Request) -> dict[str, str]:
    context = get_request_log_context(request)
    headers = {
        "x-request-id": context.request_id,
        "x-trace-id": context.trace_id,
    }
    if context.session_id is not None:
        headers["x-session-id"] = context.session_id
    if context.turn_id is not None:
        headers["x-turn-id"] = context.turn_id
    return headers


def bind_proxy_headers(
    request: Request,
    headers: Mapping[str, str] | None,
) -> RequestLogContext:
    context = get_request_log_context(request)
    if not headers:
        return context

    proxy_trace_id = _normalize_optional_string(headers.get("x-trace-id"))
    proxy_session_id = _normalize_optional_string(headers.get("x-session-id"))
    proxy_turn_id = _normalize_optional_string(headers.get("x-turn-id"))
    proxy_service_name = _normalize_optional_string(headers.get("x-service-name"))

    if proxy_trace_id is not None:
        context.trace_id = proxy_trace_id
    if proxy_session_id is not None:
        context.session_id = proxy_session_id
    if proxy_turn_id is not None:
        context.turn_id = proxy_turn_id
    if proxy_service_name is not None:
        context.upstream_service_name = proxy_service_name
    return context


def apply_response_trace_headers(response: Response, request: Request) -> None:
    context = get_request_log_context(request)
    response.headers["x-request-id"] = context.request_id
    response.headers["x-trace-id"] = context.trace_id
    response.headers["x-service-name"] = context.service_name
    if context.session_id is not None:
        response.headers["x-session-id"] = context.session_id
    if context.turn_id is not None:
        response.headers["x-turn-id"] = context.turn_id


def extract_trace_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    extracted: dict[str, str] = {}
    for header_name in TRACE_RESPONSE_HEADERS:
        header_value = _normalize_optional_string(headers.get(header_name))
        if header_value is not None:
            extracted[header_name] = header_value
    return extracted


def emit_request_log(
    request: Request,
    *,
    status_code: int,
    duration_ms: float,
    error: Any | None = None,
) -> None:
    context = get_request_log_context(request)
    payload = {
        "event": "http.request",
        "service_name": context.service_name,
        "request_id": context.request_id,
        "trace_id": context.trace_id,
        "method": context.method,
        "path": context.path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
    }
    if context.domain_id is not None:
        payload["domain_id"] = context.domain_id
    if context.action_id is not None:
        payload["action_id"] = context.action_id
    if context.session_id is not None:
        payload["session_id"] = context.session_id
    if context.turn_id is not None:
        payload["turn_id"] = context.turn_id
    if context.learner_hash is not None:
        payload["learner_hash"] = context.learner_hash
    if context.prompt_profile is not None:
        payload["prompt_profile"] = context.prompt_profile
    if context.experiment_id is not None:
        payload["experiment_id"] = context.experiment_id
    if context.upstream_service_name is not None:
        payload["upstream_service_name"] = context.upstream_service_name

    sanitized_error = _sanitize_error(error)
    if sanitized_error is not None:
        payload["error"] = sanitized_error

    LOGGER.log(
        _log_level_for_status(status_code),
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )

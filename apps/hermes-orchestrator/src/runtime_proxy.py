from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from hermes_observability import extract_trace_headers

DEFAULT_RUNTIME_API_BASE = "http://127.0.0.1:8100"
VALID_DEPLOY_ENVS = frozenset({"development", "staging", "production"})


class DeployEnv(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


def get_deploy_env() -> str:
    raw = os.getenv("DEPLOY_ENV", "development")
    if raw not in VALID_DEPLOY_ENVS:
        return "development"
    return raw


def validate_runtime_env() -> None:
    env = get_deploy_env()
    if env in ("staging", "production"):
        base = get_runtime_api_base()
        if base == DEFAULT_RUNTIME_API_BASE.rstrip("/"):
            raise RuntimeError(
                f"DEPLOY_ENV={env} requires MR_VISIT_JP_RUNTIME_BASE (or "
                f"RUNTIME_API_BASE) to be set. Refusing to use default "
                f"{DEFAULT_RUNTIME_API_BASE}."
            )


class RuntimeProxyError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeProxyResult:
    status: int
    payload: Any
    headers: dict[str, str]


def get_runtime_api_base() -> str:
    return (
        os.getenv("MR_VISIT_JP_RUNTIME_BASE")
        or os.getenv("RUNTIME_API_BASE")
        or DEFAULT_RUNTIME_API_BASE
    ).rstrip("/")


def _parse_runtime_payload(raw_text: str) -> Any:
    if not raw_text:
        return {}
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"detail": raw_text}


async def proxy_runtime_request(
    *,
    path: str,
    method: str = "GET",
    json_body: Any | None = None,
    runtime_api_base: str | None = None,
    headers: dict[str, str] | None = None,
) -> RuntimeProxyResult:
    runtime_url = f"{(runtime_api_base or get_runtime_api_base()).rstrip('/')}{path}"
    request_headers = {"accept": "application/json"}
    if headers:
        request_headers.update(headers)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=runtime_url,
                json=json_body,
                headers=request_headers,
            )
    except httpx.HTTPError as exc:
        raise RuntimeProxyError(f"runtime unavailable: {exc}") from exc

    return RuntimeProxyResult(
        status=response.status_code,
        payload=_parse_runtime_payload(response.text),
        headers=extract_trace_headers(response.headers),
    )

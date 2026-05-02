from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


DEFAULT_HERMES_BASE = "http://127.0.0.1:8000"
DEFAULT_RUNTIME_BASE = "http://127.0.0.1:8100"
DEFAULT_GP_RUNTIME_BASE = "http://127.0.0.1:8200"
TRACE_RESPONSE_HEADERS = (
    "x-request-id",
    "x-trace-id",
    "x-session-id",
    "x-turn-id",
    "x-service-name",
)


class SmokeCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class HttpResponse:
    status: int
    payload: Any
    headers: dict[str, str]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a local integration smoke check for web -> Hermes -> MR runtime plus Hermes skill-scoped GP routes.",
    )
    parser.add_argument(
        "--web-base",
        default=os.getenv("WEB_BASE_URL") or _default_web_base(),
        help="Base URL for the local web app.",
    )
    parser.add_argument(
        "--hermes-base",
        default=os.getenv("HERMES_API_BASE", DEFAULT_HERMES_BASE),
        help="Base URL for the Hermes orchestrator.",
    )
    parser.add_argument(
        "--runtime-base",
        default=os.getenv("MR_VISIT_JP_RUNTIME_BASE", DEFAULT_RUNTIME_BASE),
        help="Base URL for the MR runtime.",
    )
    parser.add_argument(
        "--gp-runtime-base",
        default=os.getenv("GP_VISIT_JP_RUNTIME_BASE", DEFAULT_GP_RUNTIME_BASE),
        help="Base URL for the GP runtime.",
    )
    parser.add_argument(
        "--learner-id",
        default=f"smoke_{datetime.now(tz=timezone.utc).strftime('%Y%m%d%H%M%S')}",
        help="Learner id used for the smoke-check session.",
    )
    parser.add_argument(
        "--message",
        default="先生の診療方針に合わせて、患者像を絞って短くご相談します。",
        help="User turn message sent during the smoke check.",
    )
    parser.add_argument(
        "--auth-user-id",
        default=os.getenv("SMOKE_AUTH_USER_ID", "learner_demo_001"),
        help="Mock auth user id used when Web runs with AUTH_MODE=mock.",
    )
    parser.add_argument(
        "--auth-password",
        default=os.getenv("SMOKE_AUTH_PASSWORD", "Welcome123"),
        help="Mock auth password used when Web runs with AUTH_MODE=mock.",
    )
    return parser


def _default_web_base() -> str:
    port = os.getenv("WEB_PORT", "3000").strip() or "3000"
    if port == "3000":
        return "http://127.0.0.1:3000"
    return f"http://127.0.0.1:{port}"


def _parse_payload(raw_text: str) -> Any:
    if not raw_text:
        return {}
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"detail": raw_text}


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _extract_trace_headers(headers: Any) -> dict[str, str]:
    extracted: dict[str, str] = {}
    for header_name in TRACE_RESPONSE_HEADERS:
        header_value = headers.get(header_name)
        if isinstance(header_value, str) and header_value.strip():
            extracted[header_name] = header_value.strip()
    return extracted


def _build_trace_headers(
    *,
    request_id: str,
    trace_id: str,
    session_id: str | None = None,
) -> dict[str, str]:
    headers = {
        "x-request-id": request_id,
        "x-trace-id": trace_id,
    }
    if session_id:
        headers["x-session-id"] = session_id
    return headers


def _format_trace_headers(headers: dict[str, str]) -> str:
    if not headers:
        return "{}"
    return json.dumps(headers, ensure_ascii=False, sort_keys=True)


def _request_json(
    *,
    method: str,
    url: str,
    json_body: Any | None = None,
    headers: dict[str, str] | None = None,
    opener: urllib.request.OpenerDirector | None = None,
    timeout: float = 30.0,
) -> HttpResponse:
    data = None
    request_headers = {"accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        request_headers["content-type"] = "application/json"

    request = urllib.request.Request(
        url=url,
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        open_request = opener.open if opener is not None else urllib.request.urlopen
        with open_request(request, timeout=timeout) as response:
            payload = _parse_payload(response.read().decode("utf-8"))
            return HttpResponse(
                status=response.getcode(),
                payload=payload,
                headers=_extract_trace_headers(response.headers),
            )
    except urllib.error.HTTPError as exc:
        payload = _parse_payload(exc.read().decode("utf-8"))
        return HttpResponse(
            status=exc.code,
            payload=payload,
            headers=_extract_trace_headers(exc.headers),
        )
    except urllib.error.URLError as exc:
        raise SmokeCheckError(f"Request failed for {url}: {exc.reason}") from exc


def _expect_json(
    *,
    service: str,
    name: str,
    method: str,
    url: str,
    trace_id: str,
    session_id: str | None = None,
    json_body: Any | None = None,
    opener: urllib.request.OpenerDirector | None = None,
    validator: Callable[[Any], None] | None = None,
) -> HttpResponse:
    request_id = _generate_id("req")
    print(
        f"[smoke-check] service={service} step={name} url={url} request_id={request_id} "
        f"trace_id={trace_id}{f' session_id={session_id}' if session_id else ''}"
    )
    try:
        response = _request_json(
            method=method,
            url=url,
            json_body=json_body,
            headers=_build_trace_headers(
                request_id=request_id,
                trace_id=trace_id,
                session_id=session_id,
            ),
            opener=opener,
        )
    except SmokeCheckError as exc:
        raise SmokeCheckError(
            f"service={service} step={name} url={url} request_id={request_id} "
            f"trace_id={trace_id}{f' session_id={session_id}' if session_id else ''} "
            f"error={exc}"
        ) from exc
    if response.status >= 400:
        raise SmokeCheckError(
            f"service={service} step={name} failed with HTTP {response.status} "
            f"url={url} request_id={request_id} trace_id={trace_id} "
            f"response_headers={_format_trace_headers(response.headers)} "
            f"payload={json.dumps(response.payload, ensure_ascii=False)}"
        )
    if validator is not None:
        try:
            validator(response.payload)
        except SmokeCheckError as exc:
            raise SmokeCheckError(
                f"service={service} step={name} validation failed "
                f"url={url} request_id={request_id} trace_id={trace_id} "
                f"response_headers={_format_trace_headers(response.headers)} "
                f"payload={json.dumps(response.payload, ensure_ascii=False)} "
                f"error={exc}"
            ) from exc
    return response


def _expect_status_ok(payload: Any) -> None:
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise SmokeCheckError(f"Expected status=ok payload, got: {payload}")


def _expect_status_value(payload: Any, expected: str) -> None:
    if not isinstance(payload, dict) or payload.get("status") != expected:
        raise SmokeCheckError(f"Expected status={expected} payload, got: {payload}")


def _expect_scenarios(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise SmokeCheckError(f"Expected scenario payload object, got: {payload}")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise SmokeCheckError(f"Expected at least one scenario, got: {payload}")


def _expect_scenarios_for_domain(payload: Any, domain_id: str) -> None:
    _expect_scenarios(payload)
    if payload.get("domain_id") != domain_id:
        raise SmokeCheckError(f"Expected domain_id={domain_id}, got: {payload}")


def _expect_session_started(payload: Any) -> None:
    if not isinstance(payload, dict) or not payload.get("session_id"):
        raise SmokeCheckError(f"Expected session_id in payload, got: {payload}")


def _expect_turn_processed(payload: Any) -> None:
    if not isinstance(payload, dict) or not payload.get("doctor_reply"):
        raise SmokeCheckError(f"Expected doctor_reply in turn payload, got: {payload}")


def _expect_finalized(payload: Any) -> None:
    if not isinstance(payload, dict) or payload.get("status") != "finalized":
        raise SmokeCheckError(f"Expected finalized payload, got: {payload}")


def _expect_progress(payload: Any, learner_id: str) -> None:
    if not isinstance(payload, dict):
        raise SmokeCheckError(f"Expected progress payload object, got: {payload}")
    if payload.get("learner_id") != learner_id:
        raise SmokeCheckError(f"Expected learner_id={learner_id}, got: {payload}")
    if int(payload.get("total_sessions", 0)) < 1:
        raise SmokeCheckError(f"Expected total_sessions >= 1, got: {payload}")


def _expect_skills(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise SmokeCheckError(f"Expected skill payload object, got: {payload}")
    skills = payload.get("skills")
    if not isinstance(skills, list):
        raise SmokeCheckError(f"Expected skills list, got: {payload}")
    expected = {"mr_visit_jp", "gp_visit_jp"}
    if not expected.issubset(set(str(item) for item in skills)):
        raise SmokeCheckError(f"Expected skills {sorted(expected)}, got: {payload}")


def _expect_review_for_skill(payload: Any, skill_id: str) -> None:
    _expect_finalized(payload)
    review = payload.get("review")
    if not isinstance(review, dict):
        raise SmokeCheckError(f"Expected review object, got: {payload}")
    meta = review.get("meta")
    if not isinstance(meta, dict):
        raise SmokeCheckError(f"Expected review.meta object, got: {payload}")
    context = meta.get("context")
    if not isinstance(context, dict):
        raise SmokeCheckError(f"Expected review.meta.context object, got: {payload}")
    if context.get("skill_id") != skill_id:
        raise SmokeCheckError(f"Expected review.meta.context.skill_id={skill_id}, got: {payload}")


def _expect_event_envelope(payload: Any) -> None:
    required_fields = {
        "type",
        "source",
        "stage",
        "content",
        "metadata",
        "skill_id",
        "session_id",
        "turn_id",
        "seq",
        "timestamp",
        "schema_version",
    }
    if not isinstance(payload, dict):
        raise SmokeCheckError(f"Expected event envelope object, got: {payload}")
    missing = sorted(required_fields - set(payload.keys()))
    if missing:
        raise SmokeCheckError(f"Event envelope missing fields {missing}: {payload}")
    if not isinstance(payload.get("content"), dict):
        raise SmokeCheckError(f"Expected event.content object, got: {payload}")
    if not isinstance(payload.get("metadata"), dict):
        raise SmokeCheckError(f"Expected event.metadata object, got: {payload}")
    if int(payload.get("seq", 0)) < 1:
        raise SmokeCheckError(f"Expected event.seq >= 1, got: {payload}")


def _auth_mode(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "disabled"
    raw = payload.get("auth_mode")
    if not isinstance(raw, str):
        return "disabled"
    normalized = raw.strip().lower()
    if normalized in {"mock", "oidc"}:
        return normalized
    return "disabled"


def _authenticated_user(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("authenticated") is not True:
        return None
    user = payload.get("user")
    if isinstance(user, dict):
        return user
    return None


def _ensure_web_auth_session(
    *,
    web_base: str,
    trace_id: str,
    opener: urllib.request.OpenerDirector,
    auth_user_id: str,
    auth_password: str,
) -> dict[str, Any] | None:
    session = _expect_json(
        service="web",
        name="web auth session",
        method="GET",
        url=f"{web_base}/api/auth/session",
        trace_id=trace_id,
        opener=opener,
    ).payload
    mode = _auth_mode(session)
    user = _authenticated_user(session)
    if mode == "disabled":
        return None
    if user is not None:
        return user
    if mode == "oidc":
        raise SmokeCheckError(
            "Web is running with AUTH_MODE=oidc and no authenticated session. "
            "Run smoke-check against AUTH_MODE=disabled/mock or provide a pre-authenticated Web session."
        )

    _expect_json(
        service="web",
        name="web mock login",
        method="POST",
        url=f"{web_base}/api/auth/login",
        trace_id=trace_id,
        json_body={"user_id": auth_user_id, "password": auth_password},
        opener=opener,
        validator=lambda payload: _expect_status_value(payload, "ok"),
    )
    session = _expect_json(
        service="web",
        name="web auth session after login",
        method="GET",
        url=f"{web_base}/api/auth/session",
        trace_id=trace_id,
        opener=opener,
    ).payload
    user = _authenticated_user(session)
    if user is None:
        raise SmokeCheckError(f"Expected authenticated mock session, got: {session}")
    return user


def run(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    web_base = args.web_base.rstrip("/")
    hermes_base = args.hermes_base.rstrip("/")
    runtime_base = args.runtime_base.rstrip("/")
    gp_runtime_base = args.gp_runtime_base.rstrip("/")
    learner_id = args.learner_id
    trace_id = _generate_id("trace")
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    authenticated_user = _ensure_web_auth_session(
        web_base=web_base,
        trace_id=trace_id,
        opener=opener,
        auth_user_id=args.auth_user_id,
        auth_password=args.auth_password,
    )
    if authenticated_user is not None:
        authenticated_learner_id = authenticated_user.get("learner_id")
        if isinstance(authenticated_learner_id, str) and authenticated_learner_id.strip():
            learner_id = authenticated_learner_id.strip()
    gp_learner_id = f"{learner_id}_gp"

    print(f"[smoke-check] web_base={web_base}")
    print(f"[smoke-check] hermes_base={hermes_base}")
    print(f"[smoke-check] runtime_base={runtime_base}")
    print(f"[smoke-check] gp_runtime_base={gp_runtime_base}")
    print(f"[smoke-check] trace_id={trace_id}")

    runtime_health = _expect_json(
        service="runtime",
        name="runtime health",
        method="GET",
        url=f"{runtime_base}/healthz",
        trace_id=trace_id,
        validator=_expect_status_ok,
    ).payload
    gp_runtime_health = _expect_json(
        service="gp-runtime",
        name="gp runtime health",
        method="GET",
        url=f"{gp_runtime_base}/healthz",
        trace_id=trace_id,
        validator=_expect_status_ok,
    ).payload
    hermes_health = _expect_json(
        service="hermes",
        name="Hermes health",
        method="GET",
        url=f"{hermes_base}/healthz",
        trace_id=trace_id,
        validator=_expect_status_ok,
    ).payload
    hermes_skills = _expect_json(
        service="hermes",
        name="Hermes skills",
        method="GET",
        url=f"{hermes_base}/v1/skills",
        trace_id=trace_id,
        validator=_expect_skills,
    ).payload
    hermes_scenarios = _expect_json(
        service="hermes",
        name="Hermes scenarios",
        method="GET",
        url=f"{hermes_base}/v1/scenarios",
        trace_id=trace_id,
        validator=_expect_scenarios,
    ).payload
    web_scenarios = _expect_json(
        service="web",
        name="web runtime proxy scenarios",
        method="GET",
        url=f"{web_base}/api/runtime/scenarios",
        trace_id=trace_id,
        opener=opener,
        validator=_expect_scenarios,
    ).payload

    hermes_scenario_ids = [
        scenario.get("id")
        for scenario in hermes_scenarios["scenarios"]
        if isinstance(scenario, dict)
    ]
    web_scenario_ids = [
        scenario.get("id")
        for scenario in web_scenarios["scenarios"]
        if isinstance(scenario, dict)
    ]
    if hermes_scenario_ids != web_scenario_ids:
        raise SmokeCheckError(
            "Scenario ids differ between service=hermes "
            f"url={hermes_base}/v1/scenarios and service=web "
            f"url={web_base}/api/runtime/scenarios: "
            f"hermes={hermes_scenario_ids} web={web_scenario_ids}"
        )

    scenario_id = str(web_scenario_ids[0])
    started_response = _expect_json(
        service="web",
        name="web start session",
        method="POST",
        url=f"{web_base}/api/runtime/sessions/start",
        trace_id=trace_id,
        json_body={"scenario_id": scenario_id, "learner_id": learner_id},
        opener=opener,
        validator=_expect_session_started,
    )
    started = started_response.payload
    session_id = str(started["session_id"])

    _expect_json(
        service="web",
        name="web get session",
        method="GET",
        url=f"{web_base}/api/runtime/sessions/{session_id}",
        trace_id=trace_id,
        session_id=session_id,
        opener=opener,
        validator=_expect_session_started,
    )
    _expect_json(
        service="web",
        name="web send turn",
        method="POST",
        url=f"{web_base}/api/runtime/sessions/{session_id}/turn",
        trace_id=trace_id,
        session_id=session_id,
        json_body={"message": args.message},
        opener=opener,
        validator=_expect_turn_processed,
    )
    _expect_json(
        service="web",
        name="web get events",
        method="GET",
        url=f"{web_base}/api/runtime/sessions/{session_id}/events",
        trace_id=trace_id,
        session_id=session_id,
        opener=opener,
        validator=lambda payload: _expect_event_count(payload, minimum=1),
    )
    _expect_json(
        service="web",
        name="web finish session",
        method="POST",
        url=f"{web_base}/api/runtime/sessions/{session_id}/finish",
        trace_id=trace_id,
        session_id=session_id,
        opener=opener,
        validator=_expect_finalized,
    )
    _expect_json(
        service="web",
        name="web get review",
        method="GET",
        url=f"{web_base}/api/runtime/sessions/{session_id}/review",
        trace_id=trace_id,
        session_id=session_id,
        opener=opener,
        validator=_expect_finalized,
    )
    progress = _expect_json(
        service="web",
        name="web get learner progress",
        method="GET",
        url=f"{web_base}/api/runtime/learners/{learner_id}/progress",
        trace_id=trace_id,
        opener=opener,
        validator=lambda payload: _expect_progress(payload, learner_id),
    ).payload
    gp_scenarios = _expect_json(
        service="hermes",
        name="Hermes GP scenarios",
        method="GET",
        url=f"{hermes_base}/v1/skills/gp_visit_jp/scenarios",
        trace_id=trace_id,
        validator=lambda payload: _expect_scenarios_for_domain(payload, "gp_visit_jp"),
    ).payload
    gp_scenario_id = str(gp_scenarios["scenarios"][0]["id"])
    gp_started = _expect_json(
        service="hermes",
        name="Hermes GP start session",
        method="POST",
        url=f"{hermes_base}/v1/skills/gp_visit_jp/sessions/start",
        trace_id=trace_id,
        json_body={"scenario_id": gp_scenario_id, "learner_id": gp_learner_id},
        validator=_expect_session_started,
    ).payload
    gp_session_id = str(gp_started["session_id"])
    _expect_json(
        service="hermes",
        name="Hermes GP send turn",
        method="POST",
        url=f"{hermes_base}/v1/skills/gp_visit_jp/sessions/{gp_session_id}/turn",
        trace_id=trace_id,
        session_id=gp_session_id,
        json_body={"message": "患者さんの生活背景を一つ確認して、今週やれる目標を一緒に決めます。"},
        validator=_expect_turn_processed,
    )
    _expect_json(
        service="hermes",
        name="Hermes GP finish session",
        method="POST",
        url=f"{hermes_base}/v1/skills/gp_visit_jp/sessions/{gp_session_id}/finish",
        trace_id=trace_id,
        session_id=gp_session_id,
        validator=lambda payload: _expect_review_for_skill(payload, "gp_visit_jp"),
    )
    _expect_json(
        service="hermes",
        name="Hermes GP get review",
        method="GET",
        url=f"{hermes_base}/v1/skills/gp_visit_jp/sessions/{gp_session_id}/review",
        trace_id=trace_id,
        session_id=gp_session_id,
        validator=lambda payload: _expect_review_for_skill(payload, "gp_visit_jp"),
    )
    gp_progress = _expect_json(
        service="hermes",
        name="Hermes GP learner progress",
        method="GET",
        url=f"{hermes_base}/v1/skills/gp_visit_jp/learners/{gp_learner_id}/progress",
        trace_id=trace_id,
        validator=lambda payload: _expect_progress(payload, gp_learner_id),
    ).payload

    print(
        f"[smoke-check] passed session_id={session_id} learner_id={learner_id} "
        f"trace_id={trace_id} "
        f"runtime_scenarios={runtime_health.get('scenario_count')} "
        f"gp_runtime_scenarios={gp_runtime_health.get('scenario_count')} "
        f"persistence_mode={runtime_health.get('persistence_mode')} "
        f"prompt_profile={runtime_health.get('prompt_profile')} "
        f"experiment_id={runtime_health.get('experiment_id')} "
        f"mr_total_sessions={progress.get('total_sessions')} "
        f"gp_total_sessions={gp_progress.get('total_sessions')}"
    )
    print(
        f"[smoke-check] Hermes skills={hermes_skills.get('skills')} "
        f"default_skill_id={hermes_health.get('default_skill_id')} "
        f"runtime_api_base={hermes_health.get('runtime_api_base')}"
    )
    return 0


def _expect_event_count(payload: Any, *, minimum: int) -> None:
    if not isinstance(payload, dict):
        raise SmokeCheckError(f"Expected event payload object, got: {payload}")
    if int(payload.get("event_count", 0)) < minimum:
        raise SmokeCheckError(f"Expected event_count >= {minimum}, got: {payload}")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise SmokeCheckError(f"Expected non-empty events list, got: {payload}")
    _expect_event_envelope(events[0])


def main() -> None:
    try:
        raise SystemExit(run())
    except SmokeCheckError as exc:
        print(f"[smoke-check] failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

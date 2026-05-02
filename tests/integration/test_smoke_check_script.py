from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_CHECK_PATH = REPO_ROOT / "scripts" / "smoke_check.py"


def _load_smoke_check_module():
    spec = importlib.util.spec_from_file_location("cosi_smoke_check", SMOKE_CHECK_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smoke_check = _load_smoke_check_module()


def test_expect_json_wraps_network_errors_with_service_and_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smoke_check, "_generate_id", lambda prefix: f"{prefix}_fixed")

    def _boom(**_: object):
        raise smoke_check.SmokeCheckError("Request failed for http://127.0.0.1:8100/healthz: refused")

    monkeypatch.setattr(smoke_check, "_request_json", _boom)

    with pytest.raises(smoke_check.SmokeCheckError) as exc_info:
        smoke_check._expect_json(
            service="runtime",
            name="runtime health",
            method="GET",
            url="http://127.0.0.1:8100/healthz",
            trace_id="trace_fixed",
            validator=smoke_check._expect_status_ok,
        )

    message = str(exc_info.value)
    assert "service=runtime" in message
    assert "step=runtime health" in message
    assert "url=http://127.0.0.1:8100/healthz" in message
    assert "request_id=req_fixed" in message
    assert "trace_id=trace_fixed" in message


def test_expect_json_wraps_validation_failures_with_service_and_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smoke_check, "_generate_id", lambda prefix: f"{prefix}_fixed")
    monkeypatch.setattr(
        smoke_check,
        "_request_json",
        lambda **_: smoke_check.HttpResponse(
            status=200,
            payload={"status": "not_ok"},
            headers={"x-service-name": "hermes-orchestrator"},
        ),
    )

    with pytest.raises(smoke_check.SmokeCheckError) as exc_info:
        smoke_check._expect_json(
            service="hermes",
            name="Hermes health",
            method="GET",
            url="http://127.0.0.1:8000/healthz",
            trace_id="trace_fixed",
            validator=smoke_check._expect_status_ok,
        )

    message = str(exc_info.value)
    assert "service=hermes" in message
    assert "step=Hermes health validation failed" in message
    assert "url=http://127.0.0.1:8000/healthz" in message
    assert 'payload={"status": "not_ok"}' in message


def test_ensure_web_auth_session_logs_in_for_mock_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    payloads = [
        {"authenticated": False, "auth_mode": "mock", "user": None},
        {"status": "ok"},
        {
            "authenticated": True,
            "auth_mode": "mock",
            "user": {
                "learner_id": "learner_demo_001",
                "org_id": None,
                "role": "learner",
                "name": "Demo Learner",
            },
        },
    ]

    def _fake_expect_json(**kwargs: object):
        calls.append(kwargs)
        return smoke_check.HttpResponse(status=200, payload=payloads.pop(0), headers={})

    monkeypatch.setattr(smoke_check, "_expect_json", _fake_expect_json)

    user = smoke_check._ensure_web_auth_session(
        web_base="http://127.0.0.1:3000",
        trace_id="trace_fixed",
        opener=object(),
        auth_user_id="learner_demo_001",
        auth_password="Welcome123",
    )

    assert user is not None
    assert user["learner_id"] == "learner_demo_001"
    assert [call["name"] for call in calls] == [
        "web auth session",
        "web mock login",
        "web auth session after login",
    ]
    assert calls[1]["json_body"] == {
        "user_id": "learner_demo_001",
        "password": "Welcome123",
    }


def test_ensure_web_auth_session_rejects_unauthenticated_oidc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_expect_json(**_: object):
        return smoke_check.HttpResponse(
            status=200,
            payload={"authenticated": False, "auth_mode": "oidc", "user": None},
            headers={},
        )

    monkeypatch.setattr(smoke_check, "_expect_json", _fake_expect_json)

    with pytest.raises(smoke_check.SmokeCheckError, match="AUTH_MODE=oidc"):
        smoke_check._ensure_web_auth_session(
            web_base="http://127.0.0.1:3000",
            trace_id="trace_fixed",
            opener=object(),
            auth_user_id="learner_demo_001",
            auth_password="Welcome123",
        )

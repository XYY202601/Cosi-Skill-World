from __future__ import annotations

import io
import json
from urllib import error as urllib_error

import pytest

from providers.model_artifact_generator import (
    ModelArtifactGenerationError,
    OpenAICompatibleArtifactGenerator,
    build_model_artifact_generator,
    load_openai_compat_prompt_contracts,
    load_runtime_prompt_context,
    parse_openai_compat_response_payload,
    summarize_prompt_context,
)


def test_load_openai_compat_prompt_contracts() -> None:
    contracts = load_openai_compat_prompt_contracts()
    assert set(contracts.keys()) == {"judge", "coach", "compliance"}
    assert contracts["judge"]["version"] == 1
    assert isinstance(contracts["coach"]["output_requirements"], list)
    assert len(contracts["compliance"]["output_requirements"]) > 0
    assert contracts["judge"]["contract_id"] == "alpha_baseline_v1:judge:v1"


def test_load_runtime_prompt_context_applies_profile_overrides() -> None:
    prompt_context = load_runtime_prompt_context(
        profile_id="alpha_coach_concise_v1",
        experiment_id="coach-canary-1",
        extra_flags=["manual_override"],
    )
    assert prompt_context["profile_id"] == "alpha_coach_concise_v1"
    assert prompt_context["experiment_id"] == "coach-canary-1"
    assert prompt_context["contracts"]["coach"]["version"] == 2
    assert "brief, behavior-specific" in prompt_context["contracts"]["coach"]["task_prompt"]
    assert any(
        "under 14 words" in item
        for item in prompt_context["contracts"]["coach"]["output_requirements"]
    )
    assert "manual_override" in prompt_context["flags"]

    summary = summarize_prompt_context(prompt_context)
    assert summary == {
        "profile_id": "alpha_coach_concise_v1",
        "experiment_id": "coach-canary-1",
        "flags": ["coach_concise_actions", "prompt_canary", "manual_override"],
        "contracts": {
            "judge": {"contract_id": "alpha_coach_concise_v1:judge:v1", "version": 1},
            "coach": {"contract_id": "alpha_coach_concise_v1:coach:v2", "version": 2},
            "compliance": {"contract_id": "alpha_coach_concise_v1:compliance:v1", "version": 1},
        },
    }


def test_parse_openai_compat_response_payload_accepts_string_content() -> None:
    payload = {
        "id": "resp_abc123",
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "judge_review": {"subskills": {}},
                            "coaching_feedback": {"version": 1},
                            "compliance_flags": [],
                        }
                    )
                }
            }
        ],
    }
    parsed = parse_openai_compat_response_payload(payload=payload, model="test-model")
    assert parsed["judge_review"] == {"subskills": {}}
    assert parsed["model_meta"]["generator"] == "openai_compat"
    assert parsed["model_meta"]["response_id"] == "resp_abc123"


def test_parse_openai_compat_response_payload_accepts_content_array_text_blocks() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "output_text", "text": '{"judge_review":{}'},
                        {"type": "output_text", "text": ',"coaching_feedback":{}'},
                        {"type": "text", "text": ',"compliance_flags":[]}'},
                    ]
                }
            }
        ]
    }
    parsed = parse_openai_compat_response_payload(payload=payload, model="test-model")
    assert isinstance(parsed, dict)
    assert parsed["compliance_flags"] == []


def test_parse_openai_compat_response_payload_preserves_partial_artifacts() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "judge_review": {"subskills": {}},
                            "compliance_flags": [],
                        }
                    )
                }
            }
        ]
    }
    parsed = parse_openai_compat_response_payload(payload=payload, model="test-model")
    assert parsed["judge_review"] == {"subskills": {}}
    assert parsed["compliance_flags"] == []
    assert "coaching_feedback" not in parsed


@pytest.mark.parametrize(
    "payload,error_message",
    [
        ({}, "choices is missing or empty"),
        (
            {"choices": [{"finish_reason": "content_filter", "message": {"content": "{}"}}]},
            "model finish_reason indicates no usable artifact",
        ),
        (
            {"choices": [{"message": {"refusal": "safety block", "content": ""}}]},
            "model refused request: safety block",
        ),
        (
            {"error": {"type": "rate_limit_exceeded", "message": "too many requests"}},
            "provider error payload: rate_limit_exceeded: too many requests",
        ),
        (
            {"choices": [{"message": {"content": "not-json"}}]},
            "Expecting value",
        ),
        (
            {"choices": [{"message": {"content": '["not-an-object"]'}}]},
            "model JSON root is not an object",
        ),
        (
            {"choices": [{"message": {"content": [{"type": "output_text"}]}}]},
            "model content list has no text fragments",
        ),
        (
            {"choices": [{"message": {"content": 123}}]},
            "model content is not a string or list",
        ),
    ],
)
def test_parse_openai_compat_response_payload_rejects_format_drift(
    payload: dict[str, object],
    error_message: str,
) -> None:
    with pytest.raises(Exception) as exc_info:
        parse_openai_compat_response_payload(payload=payload, model="test-model")
    assert error_message in str(exc_info.value)


class _FakeHTTPResponse:
    def __init__(
        self,
        payload: dict[str, object],
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self.headers = headers or {}

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _build_openai_generator(**overrides: object) -> OpenAICompatibleArtifactGenerator:
    prompt_context = load_runtime_prompt_context(profile_id="alpha_baseline_v1")
    params: dict[str, object] = {
        "api_base": "http://provider.test/v1",
        "api_key": "secret",
        "model": "test-model",
        "default_prompt_context": prompt_context,
        "timeout_sec": 3.5,
        "max_retries": 1,
        "retry_backoff_sec": 0.0,
    }
    params.update(overrides)
    return OpenAICompatibleArtifactGenerator(
        **params,
    )


def test_openai_compat_generator_retries_retryable_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[float] = []
    sleep_calls: list[float] = []

    def _fake_urlopen(request: object, timeout: float) -> _FakeHTTPResponse:
        attempts.append(timeout)
        if len(attempts) == 1:
            raise urllib_error.HTTPError(
                url="http://provider.test/v1/chat/completions",
                code=503,
                msg="Service Unavailable",
                hdrs={"Retry-After": "2", "x-request-id": "req_retry_1"},
                fp=io.BytesIO(b'{"error":"busy"}'),
            )
        return _FakeHTTPResponse(
            {
                "id": "resp_retry_ok",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "judge_review": {"subskills": {}},
                                    "coaching_feedback": {"version": 1},
                                    "compliance_flags": [],
                                }
                            )
                        }
                    }
                ],
            },
            headers={"x-request-id": "req_retry_2"},
        )

    monkeypatch.setattr("providers.model_artifact_generator.urllib_request.urlopen", _fake_urlopen)
    monkeypatch.setattr("providers.model_artifact_generator.time.sleep", sleep_calls.append)

    generator = _build_openai_generator()
    generated = generator.generate(
        turns=[],
        turn_count=0,
        scenario_focus_subskills=[],
        subskill_ids=[],
    )

    assert len(attempts) == 2
    assert sleep_calls == [2.0]
    assert generated is not None
    assert generated["model_meta"]["attempt_count"] == 2
    assert generated["model_meta"]["retry_count"] == 1
    assert generated["model_meta"]["generator"] == "openai_compat"
    assert generated["model_meta"]["provider_request_id"] == "req_retry_2"


def test_openai_compat_generator_reports_structured_refusal_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_urlopen(request: object, timeout: float) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(
            {
                "id": "resp_refused",
                "choices": [
                    {
                        "message": {
                            "refusal": "policy refusal",
                            "content": "",
                        }
                    }
                ],
            }
        )

    monkeypatch.setattr("providers.model_artifact_generator.urllib_request.urlopen", _fake_urlopen)

    generator = _build_openai_generator(max_retries=0)
    with pytest.raises(ModelArtifactGenerationError) as exc_info:
        generator.generate(
            turns=[],
            turn_count=0,
            scenario_focus_subskills=[],
            subskill_ids=[],
        )

    assert "openai_compat_parse_failed" in str(exc_info.value)
    assert exc_info.value.meta["failure_stage"] == "response_parse"
    assert exc_info.value.meta["fallback_target"] == "rule"
    assert exc_info.value.meta["attempt_count"] == 1
    assert exc_info.value.meta["generator"] == "openai_compat"


def test_openai_compat_generator_does_not_retry_non_retryable_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[float] = []
    sleep_calls: list[float] = []

    def _fake_urlopen(request: object, timeout: float) -> _FakeHTTPResponse:
        attempts.append(timeout)
        raise urllib_error.HTTPError(
            url="http://provider.test/v1/chat/completions",
            code=400,
            msg="Bad Request",
            hdrs={"x-request-id": "req_bad_1"},
            fp=io.BytesIO(b'{"error":"bad schema"}'),
        )

    monkeypatch.setattr("providers.model_artifact_generator.urllib_request.urlopen", _fake_urlopen)
    monkeypatch.setattr("providers.model_artifact_generator.time.sleep", sleep_calls.append)

    generator = _build_openai_generator(max_retries=3, retry_backoff_sec=1.5)
    with pytest.raises(ModelArtifactGenerationError) as exc_info:
        generator.generate(
            turns=[],
            turn_count=0,
            scenario_focus_subskills=[],
            subskill_ids=[],
        )

    assert len(attempts) == 1
    assert sleep_calls == []
    assert exc_info.value.meta["status_code"] == 400
    assert exc_info.value.meta["retryable"] is False
    assert exc_info.value.meta["provider_request_id"] == "req_bad_1"


def test_build_model_artifact_generator_reads_timeout_and_retry_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MR_RUNTIME_MODEL_MODE", "openai_compat")
    monkeypatch.setenv("MR_RUNTIME_MODEL_API_BASE", "http://provider.test/v1")
    monkeypatch.setenv("MR_RUNTIME_MODEL_API_KEY", "secret")
    monkeypatch.setenv("MR_RUNTIME_MODEL_NAME", "test-model")
    monkeypatch.setenv("MR_RUNTIME_MODEL_TIMEOUT_SEC", "21.5")
    monkeypatch.setenv("MR_RUNTIME_MODEL_MAX_RETRIES", "3")
    monkeypatch.setenv("MR_RUNTIME_MODEL_RETRY_BACKOFF_SEC", "0.1")

    generator = build_model_artifact_generator()
    assert isinstance(generator, OpenAICompatibleArtifactGenerator)
    assert generator.timeout_sec == 21.5
    assert generator.max_retries == 3
    assert generator.retry_backoff_sec == 0.1


@pytest.mark.parametrize(
    ("env_name", "env_value", "error_message"),
    [
        ("MR_RUNTIME_MODEL_TIMEOUT_SEC", "zero", "MR_RUNTIME_MODEL_TIMEOUT_SEC must be a number"),
        ("MR_RUNTIME_MODEL_MAX_RETRIES", "abc", "MR_RUNTIME_MODEL_MAX_RETRIES must be an integer"),
        ("MR_RUNTIME_MODEL_RETRY_BACKOFF_SEC", "-1", "MR_RUNTIME_MODEL_RETRY_BACKOFF_SEC must be >= 0.0"),
    ],
)
def test_build_model_artifact_generator_rejects_invalid_retry_env_values(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    error_message: str,
) -> None:
    monkeypatch.setenv("MR_RUNTIME_MODEL_MODE", "openai_compat")
    monkeypatch.setenv("MR_RUNTIME_MODEL_API_BASE", "http://provider.test/v1")
    monkeypatch.setenv("MR_RUNTIME_MODEL_API_KEY", "secret")
    monkeypatch.setenv("MR_RUNTIME_MODEL_NAME", "test-model")
    monkeypatch.setenv(env_name, env_value)

    with pytest.raises(RuntimeError, match=error_message):
        build_model_artifact_generator()

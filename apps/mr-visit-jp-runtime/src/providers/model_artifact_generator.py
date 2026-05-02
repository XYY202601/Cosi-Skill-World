from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from providers.prompt_assets import (
    PROMPT_ROLES,
    list_prompt_profile_ids,
    load_openai_compat_prompt_contracts,
    load_runtime_prompt_context,
    load_runtime_prompt_context_from_env,
    summarize_prompt_context,
)
from providers.prompt_renderer import render_openai_compat_prompt


RETRYABLE_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}
MAX_ERROR_DETAIL_LENGTH = 240
REQUEST_ID_HEADER_CANDIDATES = ("x-request-id", "openai-request-id", "request-id")


class ModelArtifactGenerationError(RuntimeError):
    """Structured provider failure that still allows rule fallback."""

    def __init__(self, message: str, *, meta: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.meta = dict(meta or {})


def _extract_message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments: list[str] = []
        for part in content:
            if isinstance(part, str):
                fragments.append(part)
                continue
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str):
                fragments.append(text)
        merged = "".join(fragments).strip()
        if not merged:
            raise ValueError("model content list has no text fragments")
        return merged
    raise ValueError("model content is not a string or list")


def _extract_provider_error(payload: dict[str, Any]) -> str | None:
    raw_error = payload.get("error")
    if isinstance(raw_error, str):
        normalized = raw_error.strip()
        return normalized or None
    if not isinstance(raw_error, dict):
        return None

    message = raw_error.get("message")
    error_type = raw_error.get("type")
    error_code = raw_error.get("code")
    parts = [
        str(part).strip()
        for part in (error_type, error_code, message)
        if isinstance(part, str) and part.strip()
    ]
    if not parts:
        return "provider error payload received"
    return ": ".join(parts)


def parse_openai_compat_response_payload(
    *,
    payload: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    provider_error = _extract_provider_error(payload)
    if provider_error is not None:
        raise ValueError(f"provider error payload: {provider_error}")

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("choices is missing or empty")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("choices[0] must be an object")

    finish_reason = first_choice.get("finish_reason")
    if isinstance(finish_reason, str) and finish_reason.strip().lower() in {
        "content_filter",
        "length",
    }:
        raise ValueError(f"model finish_reason indicates no usable artifact: {finish_reason}")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("choices[0].message must be an object")

    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        raise ValueError(f"model refused request: {refusal.strip()}")

    content = _extract_message_content_text(message.get("content"))
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("model JSON root is not an object")

    response_id = payload.get("id")
    model_meta: dict[str, Any] = {
        "generator": "openai_compat",
        "model": model,
    }
    if isinstance(response_id, str) and response_id:
        model_meta["response_id"] = response_id
    parsed["model_meta"] = model_meta
    return parsed


def _clamp_int(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(max_value, int(value)))


def _truncate_error_detail(value: Any, *, max_length: int = MAX_ERROR_DETAIL_LENGTH) -> str:
    normalized = " ".join(str(value).split()).strip()
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3] + "..."


def _extract_response_request_id(headers: Any) -> str | None:
    if headers is None:
        return None
    for key in REQUEST_ID_HEADER_CANDIDATES:
        try:
            value = headers.get(key)
        except Exception:
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_retry_after_seconds(raw_value: Any) -> float | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    try:
        seconds = float(normalized)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(normalized)
        except (TypeError, ValueError, IndexError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        seconds = (retry_at - datetime.now(UTC)).total_seconds()
    return max(0.0, seconds)


def _parse_float_env(name: str, default: float, *, min_value: float = 0.0) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        parsed = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if parsed < min_value:
        raise RuntimeError(f"{name} must be >= {min_value}")
    return parsed


def _parse_int_env(name: str, default: int, *, min_value: int = 0) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if parsed < min_value:
        raise RuntimeError(f"{name} must be >= {min_value}")
    return parsed


def _to_subskills(
    *,
    subskill_ids: list[str],
    focus_subskills: set[str],
    turn_count: int,
) -> dict[str, dict[str, Any]]:
    base = 2 + min(2, turn_count // 2)
    subskills: dict[str, dict[str, Any]] = {}
    for subskill_id in subskill_ids:
        score = _clamp_int(base + (1 if subskill_id in focus_subskills else 0), 0, 5)
        subskills[subskill_id] = {
            "score": score,
            "evidence": [f"Model-estimated from {turn_count} turn(s)."],
        }
    return subskills


def _priority_subskills(subskills: dict[str, dict[str, Any]], max_items: int = 3) -> list[str]:
    ordered = sorted(
        subskills.keys(),
        key=lambda key: (int(subskills[key].get("score", 0)), key),
    )
    return ordered[:max_items]


def _diagnosis_for_subskills(priority_subskills: list[str]) -> dict[str, Any]:
    mapping = {
        "opening": {
            "id": "opening_not_permission_based",
            "kind": "skill_gap",
            "severity": "medium",
            "summary": "Opening could be sharper in permission and relevance.",
            "related_subskills": ["opening"],
            "recommendation_focus": ["opening"],
        },
        "profiling": {
            "id": "insufficient_context_profiling",
            "kind": "skill_gap",
            "severity": "medium",
            "summary": "Context profiling depth is still limited.",
            "related_subskills": ["preparation", "profiling"],
            "recommendation_focus": ["profiling", "need_discovery"],
        },
        "scientific_delivery": {
            "id": "unclear_scientific_delivery",
            "kind": "skill_gap",
            "severity": "medium",
            "summary": "Scientific message clarity needs improvement.",
            "related_subskills": ["scientific_delivery"],
            "recommendation_focus": ["scientific_delivery"],
        },
        "need_discovery": {
            "id": "insufficient_need_discovery",
            "kind": "skill_gap",
            "severity": "high",
            "summary": "Need discovery should be confirmed before pitching.",
            "related_subskills": ["need_discovery", "profiling"],
            "recommendation_focus": ["need_discovery", "profiling"],
        },
        "objection_handling": {
            "id": "objection_response_gap",
            "kind": "skill_gap",
            "severity": "medium",
            "summary": "Objection responses need more direct evidence linkage.",
            "related_subskills": ["objection_handling", "scientific_delivery"],
            "recommendation_focus": ["objection_handling"],
        },
        "closing_followup": {
            "id": "weak_close_or_followup",
            "kind": "skill_gap",
            "severity": "medium",
            "summary": "Close with a clearer next-step commitment.",
            "related_subskills": ["closing_followup"],
            "recommendation_focus": ["closing_followup"],
        },
    }

    primary = []
    for subskill in priority_subskills:
        mapped = mapping.get(subskill)
        if mapped is not None:
            primary.append(mapped)
    if not primary:
        primary.append(
            {
                "id": "low_trust_or_rapport",
                "kind": "communication_gap",
                "severity": "medium",
                "summary": "Interaction trust signal can be strengthened.",
                "related_subskills": ["opening", "profiling"],
                "recommendation_focus": ["opening", "profiling"],
            }
        )
    return {
        "primary": primary[:3],
        "selection_basis": "model_generated_v1",
    }


def _coaching_feedback(priority_subskills: list[str]) -> dict[str, Any]:
    actions: list[str] = []
    for subskill in priority_subskills:
        if subskill == "opening":
            actions.append("Start with permission and one clear relevance sentence.")
        elif subskill == "profiling":
            actions.append("Ask one targeted profiling question before detail delivery.")
        elif subskill == "scientific_delivery":
            actions.append("Anchor your claim to one concrete evidence statement.")
        elif subskill == "need_discovery":
            actions.append("Confirm one unmet need before moving to product value.")
        elif subskill == "objection_handling":
            actions.append("Acknowledge objections first, then respond with evidence.")
        elif subskill == "closing_followup":
            actions.append("End with one realistic next step and explicit follow-up.")
        else:
            actions.append("Keep the conversation structured and concise.")

    if not actions:
        actions.append("Use a concise objective-opening-question-close structure.")

    return {
        "version": 1,
        "focus_subskills": priority_subskills[:3] or ["opening"],
        "next_actions": actions[:4],
    }


def _compliance_flags_from_messages(messages: list[str]) -> list[dict[str, Any]]:
    merged = "\n".join(message.lower() for message in messages)
    flags: list[dict[str, Any]] = []

    if "guarantee" in merged or "guaranteed" in merged or "100%" in merged:
        flags.append(
            {
                "rule_id": "unsupported_outcome_promise",
                "tag": "unsupported_promise",
                "severity": "high",
                "summary": "Outcome certainty was stated without supporting evidence boundaries.",
                "related_diagnosis_types": ["overclaim_or_off_label_risk"],
            }
        )
    if "competitor" in merged and ("worse" in merged or "inferior" in merged or "bad" in merged):
        flags.append(
            {
                "rule_id": "unsubstantiated_competitor_comparison",
                "tag": "unsubstantiated_competitor_comparison",
                "severity": "high",
                "summary": "Competitor comparison appears unsupported or overly absolute.",
                "related_diagnosis_types": ["objection_response_gap"],
            }
        )

    return flags[:3]


class ModelArtifactGenerator:
    def describe(self) -> dict[str, Any]:
        return {}

    def generate(
        self,
        *,
        turns: list[dict[str, Any]],
        turn_count: int,
        scenario_focus_subskills: list[str],
        subskill_ids: list[str],
        prompt_context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        raise NotImplementedError


class MockModelArtifactGenerator(ModelArtifactGenerator):
    """Deterministic stand-in for structured model outputs in Alpha."""

    def describe(self) -> dict[str, Any]:
        return {
            "generator": "mock",
            "requested_mode": "mock",
            "artifact_mode": "mock",
        }

    def generate(
        self,
        *,
        turns: list[dict[str, Any]],
        turn_count: int,
        scenario_focus_subskills: list[str],
        subskill_ids: list[str],
        prompt_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        focus_set = set(scenario_focus_subskills)
        subskills = _to_subskills(
            subskill_ids=subskill_ids,
            focus_subskills=focus_set,
            turn_count=turn_count,
        )

        priorities = _priority_subskills(subskills)
        messages = [str(turn.get("user_message", "")) for turn in turns if isinstance(turn, dict)]

        judge_review = {
            "rubric_version": 1,
            "subskills": subskills,
            "overall_score": 0,
            "overall_band": "functional",
            "strengths": [],
            "priority_subskills": priorities,
            "diagnosis": _diagnosis_for_subskills(priorities),
        }

        return {
            "judge_review": judge_review,
            "coaching_feedback": _coaching_feedback(priorities),
            "compliance_flags": _compliance_flags_from_messages(messages),
            "model_meta": self.describe(),
        }


@dataclass
class OpenAICompatibleArtifactGenerator(ModelArtifactGenerator):
    api_base: str
    api_key: str
    model: str
    default_prompt_context: dict[str, Any]
    timeout_sec: float = 15.0
    max_retries: int = 1
    retry_backoff_sec: float = 0.0

    def describe(self) -> dict[str, Any]:
        return {
            "generator": "openai_compat",
            "requested_mode": "openai_compat",
            "artifact_mode": "model",
            "model": self.model,
            "timeout_sec": self.timeout_sec,
            "max_retries": self.max_retries,
        }

    def _build_error_meta(
        self,
        *,
        stage: str,
        attempts_used: int,
        retryable: bool,
        detail: str,
        status_code: int | None = None,
        provider_request_id: str | None = None,
    ) -> dict[str, Any]:
        meta = self.describe()
        meta.update(
            {
                "failure_stage": stage,
                "attempt_count": attempts_used,
                "retry_count": max(0, attempts_used - 1),
                "retryable": retryable,
                "fallback_target": "rule",
                "error_detail": _truncate_error_detail(detail),
            }
        )
        if status_code is not None:
            meta["status_code"] = status_code
        if provider_request_id is not None:
            meta["provider_request_id"] = provider_request_id
        return meta

    def _call_endpoint(
        self,
        *,
        endpoint: str,
        body: dict[str, Any],
    ) -> tuple[dict[str, Any], int, str | None]:
        request = urllib_request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {self.api_key}",
            },
        )

        total_attempts = self.max_retries + 1
        last_error: ModelArtifactGenerationError | None = None
        for attempt in range(1, total_attempts + 1):
            try:
                with urllib_request.urlopen(request, timeout=self.timeout_sec) as response:
                    raw_body = response.read().decode("utf-8")
                    provider_request_id = _extract_response_request_id(getattr(response, "headers", None))
                payload = json.loads(raw_body)
                if not isinstance(payload, dict):
                    raise ModelArtifactGenerationError(
                        "openai_compat_call_failed[response_shape]: response payload is not an object",
                        meta=self._build_error_meta(
                            stage="response_shape",
                            attempts_used=attempt,
                            retryable=False,
                            detail="response payload is not an object",
                            provider_request_id=provider_request_id,
                        ),
                    )
                return payload, attempt, provider_request_id
            except urllib_error.HTTPError as exc:
                status_code = int(getattr(exc, "code", 0) or 0)
                retryable = status_code in RETRYABLE_HTTP_STATUS_CODES
                provider_request_id = _extract_response_request_id(getattr(exc, "headers", None))
                try:
                    body_excerpt = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    body_excerpt = ""
                detail = f"HTTP {status_code}"
                if body_excerpt.strip():
                    detail = f"{detail}: {_truncate_error_detail(body_excerpt)}"
                last_error = ModelArtifactGenerationError(
                    f"openai_compat_call_failed[http_{status_code}] after {attempt} attempt(s): {detail}",
                    meta=self._build_error_meta(
                        stage="http_error",
                        attempts_used=attempt,
                        retryable=retryable,
                        detail=detail,
                        status_code=status_code,
                        provider_request_id=provider_request_id,
                    ),
                )
                retry_after_delay = _parse_retry_after_seconds(
                    getattr(exc, "headers", {}).get("Retry-After")
                    if getattr(exc, "headers", None) is not None
                    else None
                )
            except (urllib_error.URLError, TimeoutError) as exc:
                detail = getattr(exc, "reason", exc)
                last_error = ModelArtifactGenerationError(
                    f"openai_compat_call_failed[network] after {attempt} attempt(s): {_truncate_error_detail(detail)}",
                    meta=self._build_error_meta(
                        stage="network_error",
                        attempts_used=attempt,
                        retryable=True,
                        detail=str(detail),
                    ),
                )
                retry_after_delay = None
            except json.JSONDecodeError as exc:
                last_error = ModelArtifactGenerationError(
                    f"openai_compat_call_failed[response_decode] after {attempt} attempt(s): {exc}",
                    meta=self._build_error_meta(
                        stage="response_decode",
                        attempts_used=attempt,
                        retryable=True,
                        detail=str(exc),
                    ),
                )
                retry_after_delay = None

            if last_error is None:
                continue
            if not last_error.meta.get("retryable") or attempt >= total_attempts:
                raise last_error
            sleep_seconds = max(
                self.retry_backoff_sec,
                retry_after_delay if retry_after_delay is not None else 0.0,
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        raise last_error or ModelArtifactGenerationError(
            "openai_compat_call_failed[unknown]: request failed",
            meta=self._build_error_meta(
                stage="unknown",
                attempts_used=total_attempts,
                retryable=False,
                detail="request failed",
            ),
        )

    def generate(
        self,
        *,
        turns: list[dict[str, Any]],
        turn_count: int,
        scenario_focus_subskills: list[str],
        subskill_ids: list[str],
        prompt_context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        effective_prompt_context = prompt_context or self.default_prompt_context
        prompt_contracts = effective_prompt_context.get("contracts", {})
        if not isinstance(prompt_contracts, dict) or not prompt_contracts:
            raise RuntimeError("prompt_context_missing_contracts")

        rendered_prompt = render_openai_compat_prompt(
            prompt_contracts=prompt_contracts,
            prompt_context=effective_prompt_context,
            turns=turns,
            turn_count=turn_count,
            scenario_focus_subskills=scenario_focus_subskills,
            subskill_ids=subskill_ids,
        )
        body = rendered_prompt.to_request_body(model=self.model)

        endpoint = self.api_base.rstrip("/") + "/chat/completions"
        payload, attempts_used, provider_request_id = self._call_endpoint(endpoint=endpoint, body=body)

        try:
            parsed = parse_openai_compat_response_payload(payload=payload, model=self.model)
        except Exception as exc:
            raise ModelArtifactGenerationError(
                f"openai_compat_parse_failed after {attempts_used} attempt(s): {exc}",
                meta=self._build_error_meta(
                    stage="response_parse",
                    attempts_used=attempts_used,
                    retryable=False,
                    detail=str(exc),
                ),
            ) from exc

        merged_meta = self.describe()
        raw_meta = parsed.get("model_meta")
        if isinstance(raw_meta, dict):
            merged_meta.update(raw_meta)
        merged_meta.update(
            {
                "attempt_count": attempts_used,
                "retry_count": max(0, attempts_used - 1),
            }
        )
        if provider_request_id is not None:
            merged_meta["provider_request_id"] = provider_request_id
        parsed["model_meta"] = merged_meta
        return parsed


def build_model_artifact_generator() -> ModelArtifactGenerator | None:
    mode = os.getenv("MR_RUNTIME_MODEL_MODE", "mock").strip().lower()

    if mode == "disabled":
        return None

    if mode == "openai_compat":
        api_base = os.getenv("MR_RUNTIME_MODEL_API_BASE", "").strip()
        api_key = os.getenv("MR_RUNTIME_MODEL_API_KEY", "").strip()
        model = os.getenv("MR_RUNTIME_MODEL_NAME", "").strip()
        if not api_base or not api_key or not model:
            raise RuntimeError(
                "openai_compat mode requires MR_RUNTIME_MODEL_API_BASE, "
                "MR_RUNTIME_MODEL_API_KEY, and MR_RUNTIME_MODEL_NAME"
            )
        timeout_sec = _parse_float_env("MR_RUNTIME_MODEL_TIMEOUT_SEC", 15.0, min_value=0.1)
        max_retries = _parse_int_env("MR_RUNTIME_MODEL_MAX_RETRIES", 1, min_value=0)
        retry_backoff_sec = _parse_float_env(
            "MR_RUNTIME_MODEL_RETRY_BACKOFF_SEC",
            0.0,
            min_value=0.0,
        )
        default_prompt_context = load_runtime_prompt_context_from_env()
        return OpenAICompatibleArtifactGenerator(
            api_base=api_base,
            api_key=api_key,
            model=model,
            default_prompt_context=default_prompt_context,
            timeout_sec=timeout_sec,
            max_retries=max_retries,
            retry_backoff_sec=retry_backoff_sec,
        )

    # Default Alpha mode uses deterministic mock model artifacts.
    return MockModelArtifactGenerator()

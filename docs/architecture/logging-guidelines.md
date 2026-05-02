# Logging Guidelines

This document defines the shared local-first logging policy for the current
Alpha stack before a reusable logging package exists.

## Goals

- trace one request across Web proxy, Hermes, and runtime
- trace one learner session across multiple HTTP requests
- keep logs searchable without leaking request bodies, prompts, or secrets

## Trace Model

Current services emit one structured JSON log line per HTTP request with these
core fields when available:

- `service_name`
- `request_id`
- `trace_id`
- `session_id`
- `turn_id`
- `domain_id`
- `action_id`
- `prompt_profile`
- `experiment_id`
- `status_code`
- `duration_ms`

`request_id` is per-HTTP-request. `trace_id` is the longer-running correlation
id that should survive the full smoke-check flow and a learner session.

## Response Headers

Current HTTP services also expose tracing headers for local debugging:

- `X-Request-ID`
- `X-Trace-ID`
- `X-Session-ID`
- `X-Turn-ID`
- `X-Service-Name`

Hermes and the Web proxy forward request/trace context downstream and then
update their own response headers from upstream trace context when a session
already exists.

## Field Policy

Allowed in plain logs:

- `request_id`
- `trace_id`
- `session_id`
- `turn_id`
- `domain_id`
- `action_id`
- `prompt_profile`
- `experiment_id`
- HTTP method/path/status/duration
- upstream service name

Hashed before logging:

- `learner_id` is logged only as `learner_hash`

Never log:

- raw user turn text
- model prompts or rendered prompt bodies
- provider tokens, API keys, bearer tokens, cookies, or authorization headers
- raw request/response bodies unless a future task adds an explicit redacted
  debug dump path

## Smoke Check Contract

`scripts/smoke_check.py` now generates a run-level `trace_id` and per-request
`request_id` values. On failure it reports:

- the URL that failed
- request and trace ids
- returned trace headers
- the response payload

That output should be enough to locate the matching Web, Hermes, and runtime
log lines locally.

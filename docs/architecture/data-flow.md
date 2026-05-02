# Data Flow

1. Web requests a session start through Hermes orchestrator.
2. Web proxy generates or forwards `request_id` / `trace_id` headers and logs a
   local structured request line without request bodies.
3. Hermes resolves `mr_visit_jp` package, forwards trace headers to runtime, and
   logs the proxied request with the same correlation fields.
4. Runtime loads scenario assets from `domains/mr_visit_jp`.
5. Runtime binds the active `trace_id` into session context, persisted events,
   and review metadata, then logs the request with session-aware fields.
6. Runtime writes transcripts/events via services.
7. Runtime evaluates and returns review/diagnosis/progression.
8. Hermes exposes normalized review/progress back to web and keeps the tracing
   headers on the response path.

See `docs/architecture/logging-guidelines.md` for the current redaction and
correlation policy.

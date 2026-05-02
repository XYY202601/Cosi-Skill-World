# session-store

Persistence layer for training sessions.

## Purpose

Provide a clean interface to create, load, update, and finalize sessions.

## Current Surface

- Alpha adapter: `apps/mr-visit-jp-runtime/src/persistence/file_session_store.py`
- Runtime contract: `apps/mr-visit-jp-runtime/src/persistence/interfaces.py`

## Responsibilities

- session persistence
- turn/transcript persistence coordination
- session status transitions
- review payload storage
- prompt context linkage
- replay-safe ordering

## SQL Target

- `sessions`
- `session_turns`
- `session_reviews`
- `prompt_context_snapshots`

See `docs/architecture/session-store-search-blueprint.md` for the reviewed
column and index target.

## Boundary Rule

`SessionStore` stays a write/read-by-id contract.
Supervisor search and free-text search should land in separate query surfaces,
not inside the write adapter.

## Why Separate

The runtime should not directly scatter persistence code everywhere.
This service keeps session access centralized.

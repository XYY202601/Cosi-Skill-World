# shared-types

Shared type definitions used across frontend and backend services.

## Purpose

Keep service contracts explicit and consistent.

## Typical Content

- session DTOs
- review DTOs
- progress DTOs
- diagnosis DTOs
- skill package metadata types

## Rule

No business logic here.
Types only.

## Current Contract Split

Current API contract ownership is intentionally split by concern:

- Runtime response construction and request validation live in
  `apps/mr-visit-jp-runtime/src/main.py`
- Cross-service JSON response schemas live in `packages/shared-schemas/schemas/`
- The active Web TypeScript mirror currently lives in
  `apps/web/src/lib/runtime-api.ts`

`packages/shared-types` is not yet wired as a buildable workspace package, so it
documents the intended home for shared TypeScript DTOs but does not replace the
active Web mirror yet.

## Compatibility Rules

- Additive response fields are allowed only when existing required fields keep
  the same meaning and shape.
- Removing a field, changing its type, or moving a nested field is a breaking
  change.
- Any Web-visible payload change must update the corresponding JSON schema and
  the Web TypeScript mirror in `apps/web/src/lib/runtime-api.ts`, or include an
  explicit compatibility note in API docs.
- Hermes must preserve upstream status codes and payload bodies for proxied
  runtime responses.

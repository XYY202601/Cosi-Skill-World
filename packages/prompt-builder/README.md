# prompt-builder

Prompt assembly and versioning utilities.

## Purpose

Build prompts from reusable domain-aware components rather than inline strings.

## Responsibilities

- load prompt templates
- merge role prompt + scenario context + policy constraints
- attach output formatting contracts
- support prompt versioning

## Design Principle

Prompts should be:
- modular
- file-based
- diffable
- testable
- versioned

Current runtime guardrails before this package absorbs more logic:
- prompt asset lookup is file-based and deterministic
- profile overrides must bump contract versions when they change prompt content
- runtime boot validates prompt assets before serving sessions
- rendered prompt payloads are snapshot-tested in the domain runtime

## Current Scope

- Generic prompt asset manager:
  - provider-specific contract lookup
  - profile override validation
  - deterministic cache invalidation
  - prompt context summary helpers
- OpenAI-compatible prompt renderer:
  - system prompt composition
  - deterministic JSON user payload assembly
  - request-body generation for `/chat/completions`

The package owns prompt loading/rendering mechanics. Domain runtimes still own:

- prompt asset locations under `domains/`
- domain-specific role sets
- experiment env var names
- model-provider transport and error handling

## Current Runtime Integration

`apps/mr-visit-jp-runtime/src/providers/prompt_assets.py` and
`apps/mr-visit-jp-runtime/src/providers/prompt_renderer.py` are thin wrappers over this
package. That keeps the MR runtime API stable while moving shared logic here.

## Tests

- package-level regression tests: `packages/prompt-builder/tests/`
- rendered prompt snapshots: `tests/fixtures/prompt_snapshots/`
- runtime startup validation still verifies prompt assets are checked at boot

# Reference Adoption Template

Use this template whenever COSI copies or closely adapts a small utility,
snippet, schema shape, or design pattern from `references/hermes-agent` or
`references/deeptutor`.

Do not use this template to justify copying a large subsystem. Large reference
copies are out of scope for this repository.

## Required Fields

- Date:
- Owner:
- Target task / PR:
- Source repository:
- Source file path:
- Source license:
- Adoption type:
  - `copy`
  - `close adaptation`
  - `design-only reimplementation`
- Reason this was needed:
- Why a fresh reimplementation was not enough:
- COSI target file path(s):
- Boundary check:
  - Confirm no runtime imports from `references/`
  - Confirm Hermes stays thin if Hermes-inspired
  - Confirm domain logic stays in the domain runtime if domain-inspired
- Attribution added where:
- Tests added or updated:
- Reviewer:

## Short Example

- Date: 2026-04-24
- Owner: codex
- Target task / PR: Q0 reference guardrails
- Source repository: `references/hermes-agent`
- Source file path: `tools/registry.py`
- Source license: MIT
- Adoption type: `design-only reimplementation`
- Reason this was needed: define a COSI-native registry vocabulary
- Why a fresh reimplementation was not enough: we needed a documented mapping to
  an approved reference pattern
- COSI target file path(s): `docs/architecture/reference-mapping.md`
- Boundary check: passed
- Attribution added where: architecture docs
- Tests added or updated: n/a
- Reviewer: pending

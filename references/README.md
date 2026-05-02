# references

This directory stores **read-only reference implementations** used for research and architectural comparison.

## Included Repositories

- `hermes-agent/` (MIT)
- `deeptutor/` (Apache-2.0)

## Purpose

These repositories are used to:
- study architecture
- compare abstractions
- inspect implementation details
- extract reusable design patterns
- evaluate small utilities for possible attributed adaptation

## What NOT to do

Do not:
- import production code directly from here
- tightly couple our runtime to these repositories
- treat them as embedded subsystems
- modify them as part of product development
- copy large subsystems into `apps/`, `packages/`, `services/`, or `domains/`

## What to do instead

- document learnings in `docs/adrs/`
- keep the adoption matrix in `docs/architecture/reference-mapping.md`
- record copied/adapted snippets with `docs/architecture/reference-adoption-template.md`
- re-implement only what fits our product boundary
- vendor or adapt only tiny utilities when explicitly approved, attributed, and tested

## Current Mapping

- Hermes-agent inspires:
  - thin orchestration boundary
  - central registry and command/action metadata
  - SQLite session/search patterns
  - doctor diagnostics and local process management
  - session-aware logging and prompt/context discipline

- DeepTutor inspires:
  - Tools vs Capabilities separation
  - unified context
  - stream event envelope
  - manifest-driven capability loading
  - learning memory/workspace concepts

## Rule

References influence design.
They do not define our runtime.

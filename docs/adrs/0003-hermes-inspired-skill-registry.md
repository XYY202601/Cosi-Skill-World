# ADR 0003: Hermes-inspired Skill Registry

## Status
Accepted

## Context
The platform needs a deterministic way to discover and route domain packages.

## Decision
Implement a local `skill-registry` package with explicit action contracts and manifest validation.

## Consequences
- predictable routing
- reduced prompt-level ambiguity
- easier multi-domain expansion

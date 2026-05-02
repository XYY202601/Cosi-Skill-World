# ADR 0001: Hermes is a Thin Orchestrator

## Status
Accepted

## Context
The product requires a platform-level AI coordinator and multiple domain-specific training runtimes.

## Decision
Hermes will remain a thin orchestrator and will not manage turn-level domain training sessions.

## Consequences
- clearer boundaries
- better runtime stability
- easier domain expansion
- less prompt sprawl inside the platform layer

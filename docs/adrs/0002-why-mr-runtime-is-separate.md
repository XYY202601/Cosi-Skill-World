# ADR 0002: MR Runtime Is a Separate Service

## Status
Accepted

## Context
Turn-level domain runtime changes faster and carries specialized prompt/scenario logic.

## Decision
`mr-visit-jp-runtime` remains separate from the platform orchestrator to preserve modularity.

## Consequences
- independent release cadence
- easier debugging of domain loops
- cleaner ownership boundaries

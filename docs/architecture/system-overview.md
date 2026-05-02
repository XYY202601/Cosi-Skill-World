# System Overview

## Runtime Chain

User
-> apps/web
-> apps/hermes-orchestrator
-> apps/mr-visit-jp-runtime
-> services/* + packages/* + domains/*

## Guiding Rule

References are architecture inputs only. Runtime code paths never import from
`references/`; copied or closely adapted code must follow
`docs/architecture/reference-mapping.md`.

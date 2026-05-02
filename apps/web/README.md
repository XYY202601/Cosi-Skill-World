# web

User-facing frontend for `cosi-skill-world`.

## Responsibility

This app provides the product UI for:
- home dashboard
- scenario selection
- training session interaction
- session review
- learner progress visualization

## Current Scope

- The current user-facing Alpha flow is still optimized for Japanese MR Visit Training (`mr_visit_jp`).
- Hermes can now list multiple skills, including the second-domain spike `gp_visit_jp`.
- A true multi-domain UI entry point has not landed yet; the web app still defaults to the MR flow.

## Non-Goals

This app does not:
- implement scoring logic
- implement agent orchestration
- store authoritative session state
- own domain evaluation rules

Those responsibilities belong to backend services.

## Main Screens

- `/` home
- `/scenarios` scenario selection
- `/sessions/:id` session interaction
- `/sessions/:id/review` review page
- `/progress` skill growth page

## Data Sources

- `apps/hermes-orchestrator` is the default backend boundary for the web app.
- `apps/mr-visit-jp-runtime` stays behind Hermes for domain execution.
- `apps/gp-visit-jp-runtime` is reachable through Hermes skill-scoped APIs, but the web UI does not expose a dedicated GP navigation flow yet.
- In local development, the web proxy falls back to `mr-visit-jp-runtime` if Hermes is unavailable.

## UI Principles

- clear training objective
- low friction session flow
- explicit diagnosis
- visible skill growth
- minimal decorative complexity in Alpha

## Future

Potential future features:
- world map
- coach persona continuity
- streak system
- achievements
- multi-domain entry point

## Dev Note

If Next reports a missing module under `.next/server/webpack-runtime.js`, remove the local cache and restart:
- `pnpm clean`
- `pnpm dev:clean`

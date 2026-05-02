# Second Domain Spike Review

## Status

Current date: 2026-04-27

`gp_visit_jp` is now a running second-domain architecture spike. The manifest is
enabled, Hermes lists it alongside `mr_visit_jp`, and the spike has its own
runtime contract path instead of piggybacking on MR.

## What Landed

- A separate `gp_visit_jp` domain folder exists under `domains/`.
- The spike has its own manifest, 2 scenario assets, 2 personas, 3 domain-owned
  subskills, minimal prompt assets, rubric, and compliance policy.
- `apps/gp-visit-jp-runtime` now implements the minimum shared runtime contract
  with deterministic in-memory behavior.
- Hermes skill summaries and skill-scoped routes now work for both
  `mr_visit_jp` and `gp_visit_jp`.
- Local developer scripts can start, inspect, and smoke-check both runtimes in
  one stack.

## What This Proved

- Skill manifests cannot assume MR's seven subskills. Shared manifest schema
  must allow domain-owned subskill ids and optional standardized actions.
- The shared runtime contract is reusable across domains that have different
  subskills, personas, pacing, and review heuristics.
- Registry-based routing must resolve runtime bases per skill. A single fallback
  base URL is unsafe once more than one runtime exists.
- Hermes can stay thin while still listing, routing, and health-reporting more
  than one skill.
- Turn logic, scoring, review phrasing, and compliance interpretation are still
  domain-owned. GP did not need to import MR evaluation internals to satisfy the
  contract.

## What Remains Open

- The web UI is still MR-first. A genuine multi-domain selection UI is a later
  product step, not part of this spike.
- GP runtime persistence is intentionally in-memory only. Production storage
  should wait for a real second-product decision, not this spike.
- Shared package extraction beyond registry/schema vocabulary should still wait
  for repeated pressure from multiple domains.

## Rejected Premature Abstractions

- Do not generalize MR scoring or visit-flow heuristics into shared packages yet.
- Do not force GP onto MR persistence, prompt manager, or evaluation-core just
  to make the architecture look uniform.
- Do not treat "multi-skill backend" as proof that the web app already has a
  finished multi-domain UX.

## Proven Shared Abstractions

- Skill manifest vocabulary and schema validation
- Required/optional runtime action ids
- Hermes registry-based route resolution and skill summaries
- Shared response schema validation for runtime surfaces such as `/healthz`

## Still Domain-Owned

- Scenario assets and personas
- Review heuristics and scoring logic
- Compliance policy interpretation
- Progress mutation logic

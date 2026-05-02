# Reference Mapping And Adoption Plan

This document records how `references/hermes-agent` and `references/deeptutor`
should influence COSI Skill World. It is an architecture input, not a runtime
dependency list.

## Adoption Boundary

- `references/hermes-agent` is MIT licensed.
- `references/deeptutor` is Apache-2.0 licensed.
- Runtime code must not import from `references/`.
- Direct code copy is allowed only for small, isolated utilities after an explicit
  adoption note is added to the task or ADR.
- Any copied or closely adapted code must keep source attribution, license notice,
  and tests proving it fits COSI boundaries.
- Prefer reimplementation of patterns over wholesale copying.

## COSI Product Target

COSI is a skill-growth operating system:

1. package domain-specific practice capabilities
2. run structured training sessions
3. collect durable behavioral evidence
4. generate review, memory, and next-practice recommendations
5. repeat across domains through a thin platform layer

The first domain remains `mr_visit_jp`. The references should help us build the
platform spine around it without turning Hermes into the training engine or
turning the Web app into the source of authority.

## Hermes-Agent Patterns To Reuse

### Central Registries

Hermes has strong single-source registries for tools and slash commands. COSI
should adapt this into:

- `packages/skill-registry`: domain skill manifests, action contracts, health
  checks, and route targets.
- Future `packages/action-registry` or equivalent: canonical action metadata for
  Web, Hermes, tests, and docs.
- No hard-coded primary-skill routing once registry routing lands.

### Session Store And Search

Hermes' SQLite store uses WAL, schema versioning, full-text search, session
metadata, and retry-aware writes. COSI should adapt the persistence ideas, not
the agent transcript model:

- SQL mode should preserve sessions, turns, events, reviews, progress snapshots,
  prompt profile, learner id, and domain id.
- Add FTS/search only after event/review payloads are stable enough to query.
- Keep file mode as an Alpha implementation behind the same store interfaces.
- The approved Phase R5 schema target lives in
  `docs/architecture/session-store-search-blueprint.md`.

### Diagnostics And Local Operations

Hermes' doctor/process/logging patterns are directly useful for local stack
quality:

- Add a COSI doctor command or script that validates Python, Node/pnpm, ports,
  env files, provider config, domain assets, and service health.
- Treat `stack-up`, `stack-status`, `stack-down`, and `smoke-check` as a managed
  local process surface with clear logs and stale PID handling.
- Add session/request correlation and redaction rules before production logs.

### Prompt And Context Discipline

Hermes has robust prompt assembly and context-compression boundaries. COSI should
use the principles where they match training:

- Keep prompt assembly deterministic and snapshot-testable.
- Treat compacted memory/history as reference, not active instruction.
- Scan or validate loaded domain prompt/context assets before injecting them into
  model calls.

## DeepTutor Patterns To Reuse

### Tools Versus Capabilities

DeepTutor separates atomic tools from multi-step capabilities. COSI should map
this to:

- Tools: reusable atomic services such as search, evaluator helpers, prompt
  rendering, evidence extraction, event replay, migration, and diagnostics.
- Capabilities: domain training packages such as `mr_visit_jp.practice_session`,
  `mr_visit_jp.review`, `mr_visit_jp.progress`, and future domains.
- Hermes routes capabilities; domain runtimes execute them.

### Unified Context

DeepTutor's `UnifiedContext` is a good model for reducing parameter drift. COSI
should introduce a domain turn context with:

- `session_id`, `turn_id`, `learner_id`, `domain_id`, `scenario_id`
- active capability/action
- prompt profile and experiment id
- scenario, persona, compliance, and playbook context
- continuity brief and learner memory references
- locale/language and UI channel
- request metadata and trace ids

### Stream Event Protocol

DeepTutor's `StreamEvent` and `StreamBus` are useful for future live UI and
analytics, but COSI should first stabilize MR event names:

- Define a canonical COSI event envelope with type, source, stage, content,
  metadata, session id, turn id, sequence, and timestamp.
- Map MR-specific events into this envelope.
- Later use the same envelope for WebSocket streaming, replay, analytics, and
  model/tool traces.

### Plugin/Capability Loader

DeepTutor's manifest-driven loader validates how a multi-domain future should
work:

- Domain manifests should declare supported capabilities/actions.
- Domain assets should be validated before runtime registration.
- Plugin-like discovery belongs in platform packages and Hermes routing, not in
  MR-specific business logic.

### Learning Workspace

DeepTutor's memory, notebook, knowledge-base, and book concepts are future COSI
learning-workspace inputs:

- Use memory for durable learner tendencies and teaching plans.
- Use notebook/book concepts later for evidence collections, supervisor notes,
  and domain learning materials.
- Do not add a general notebook shell before review evidence and progress logic
  are stable.

## Project Structure Review

Current structure is directionally correct:

- `apps/web` owns presentation and local UI flow.
- `apps/hermes-orchestrator` is thin proxy/orchestrator.
- `apps/mr-visit-jp-runtime` owns MR session, review, progress, and recommendation
  logic.
- `domains/mr_visit_jp` owns domain assets.
- `packages/*` and `services/*` are mostly skeletons and documentation.

Required corrections:

- Split the 500+ line MR runtime `main.py` after contract consolidation into
  route modules and boot wiring, without moving domain logic out of the runtime.
- Turn `packages/skill-registry`, `shared-schemas`, `evaluation-core`,
  `prompt-builder`, and `memory-core` into real packages only when a task needs
  the boundary.
- Decide whether `services/*` remain architecture docs or become deployable
  services. Until then, keep production code inside app-owned modules and package
  libraries.
- Avoid putting DeepTutor-style generic learning shell features into Web before
  MR evidence, replay, and progress paths are strong.

## Target Structure

```text
apps/
  web/                         # UI only; no authoritative training state
  hermes-orchestrator/         # thin skill/capability routing and health
  mr-visit-jp-runtime/         # MR domain runtime and API
domains/
  mr_visit_jp/                 # MR assets, manifest, prompts, rubrics, policy
packages/
  skill-registry/              # skill/capability/action manifest validation
  shared-schemas/              # JSON schemas and compatibility tests
  shared-types/                # generated or hand-maintained TS/Python type refs
  evaluation-core/             # reusable deterministic scoring helpers
  memory-core/                 # learner memory and continuity data structures
  prompt-builder/              # deterministic prompt rendering
services/
  event-store/                 # service contract docs now; code after store split
  session-store/
  progress-service/
  recommendation-service/
docs/
  architecture/
  adrs/
references/                    # read-only sources for architecture comparison
```

## What We Intentionally Do Not Adopt

- Hermes' full autonomous agent loop inside MR sessions.
- Hermes command surface as the learner product interface.
- DeepTutor's broad product shell before COSI's MR training loop is strong.
- Generic plugins that can bypass domain asset validation.
- Reference repositories as submodules or runtime dependencies.

## Adoption Checklist For Future Tasks

Before copying or closely adapting reference code:

1. Confirm the source license and file path.
2. Explain why reimplementation is not enough.
3. Copy only the minimal isolated utility or pattern.
4. Add attribution in code comments or docs.
5. Add tests at the COSI boundary.
6. Ensure `rg "references/" apps packages services domains` does not reveal
   runtime imports.

Use [reference-adoption-template.md](/home/sunos/projects/Cosi-Skill-World/docs/architecture/reference-adoption-template.md)
to record the adoption note.

# COSI Skill World Master TODO

This file is the execution roadmap for AI engineers working in this repository.
It is intentionally more specific than a product wish list: each section explains
what to build, where to build it, how to verify it, and which boundaries must not
be crossed.

## 0. Project Understanding

### North Star

`COSI Skill World` is not a generic chatbot and not only an MR training demo.
It is a skill-growth operating system:

1. diagnose observable behavior
2. run structured practice
3. generate evidence-backed feedback
4. update long-term learner memory
5. recommend the next practice step
6. repeat across many skill domains

The first production-like domain is `mr_visit_jp`: Japanese MR visit training.
The current Alpha proves the core loop in text. The long-term platform must let
future domains package their own scenarios, rubrics, compliance rules, prompt
contracts, progression models, and coaching memory while keeping platform
routing clean.

### Three-Layer Product Architecture

COSI should be developed as three cooperating layers:

1. Training Runtime Layer
   - Owns scenario execution, persona behavior, live turns, Director guidance, Doctor response, event signals, and session completion.
   - Core question: is the practice realistic, structured, and controllable?

2. Diagnosis & Learning Layer
   - Owns evidence-linked judging, diagnosis, compliance signal interpretation, coach feedback, teaching plans, learner memory, and practice path recommendations.
   - Core question: does the learner know what to improve next and why?

3. Platform & Operations Layer
   - Owns skill registry, runtime contracts, persistence, identity, organization boundaries, supervisor/admin views, CI, deployment, and model operations.
   - Core question: can multiple domains, learners, and environments run safely and consistently?

Near-term roadmap decisions should prioritize the Diagnosis & Learning Layer once the basic runtime loop is stable. The platform is valuable only if it turns practice into measurable skill growth.

### Current Baseline Already Landed

Do not rebuild these from scratch unless a task explicitly asks for refactoring.

- [x] Fixed 8-scenario `mr_visit_jp` domain bundle with manifest, scenarios, personas, skill model, diagnosis types, compliance rules, prompt profiles, and evaluation gates.
- [x] Runtime asset validation on boot.
- [x] Runtime APIs for scenarios, session start, turn, finish, review, events, progress, and evaluation gates.
- [x] Full text session loop with Director/Doctor v1, structured review generation, local persistence, resume/review lookup, and progress update.
- [x] 7-subskill scoring, diagnosis, compliance flags, coach feedback, next-scenario recommendation, recurring weakness clusters, coach continuity, and learner memory.
- [x] Hermes as a thin orchestrator/proxy with skill-scoped routes and runtime contract tests.
- [x] Web Alpha path: home, scenarios, live session, records, record detail, review, progress.
- [x] Read-only admin operations view for prompt rollout/evaluation gates plus `make validate-content` asset diagnostics.
- [x] Prompt profile registry, experiment context, offline/online rollout gates, and promotion/blocking enforcement.
- [x] Demo learner seed data for `learner_demo_001`, `learner_demo_300`, and `learner_demo_1000`.
- [x] Developer setup commands: `make bootstrap`, `make stack-up`, `make stack-status`, `make smoke-check`, `make stack-down`, and `make seed-mr-visit-jp`.

### Architecture Guardrails

These are hard constraints for all future tasks.

- Hermes remains thin. It routes skills and exposes platform-level boundaries; it must not own MR turn-level roleplay, scoring, diagnosis, compliance, or progression.
- Domain runtime owns turn-level domain logic. For MR, that means `apps/mr-visit-jp-runtime` and `domains/mr_visit_jp`.
- Domain assets stay under `domains/`. Do not scatter scenarios, rubrics, compliance rules, or prompt contracts into Web or Hermes.
- Structured outputs must be validated before persistence and before exposing review artifacts.
- File persistence is allowed in Alpha, but production persistence must be introduced behind store interfaces, not by leaking database code across runtime logic.
- `references/hermes-agent` and `references/deeptutor` are approved architecture references, not runtime dependencies.
- Do not import runtime code from `references/`.
- If a task copies or closely adapts reference code, it must be small, isolated, attributed, license-compatible, and covered by tests at the COSI boundary.
- All reference-derived design decisions must point back to `docs/architecture/reference-mapping.md` or a specific ADR.
- Web may display and orchestrate UI state, but backend services own authoritative session, review, progress, and recommendation state.
- Shared packages must stay clean:
  - `shared-types`: types only
  - `shared-schemas`: schemas only
  - `skill-registry`: registry and manifest validation only
  - `memory-core`: memory structures only, no routing/scoring
  - `evaluation-core`: normalization/evaluation, no HTTP or UI
  - `prompt-builder`: prompt assembly/versioning, no runtime side effects

### Training Role Ownership Boundaries

The MR training loop uses several role-like components. Their responsibilities must stay separate:

| Component | Owns | Must not own | Inputs | Outputs |
| --- | --- | --- | --- | --- |
| Doctor | Persona-grounded doctor response and pushback | Final scoring, progress updates, recommendations | Scenario, persona, learner turn, playbook, session context | Doctor reply, pushback signal, local conversation pressure |
| Director | Turn-level training guidance and session flow signals | Final score, learner progress mutation, long-term recommendation policy | Transcript, playbook, continuity brief, event history | Next-turn guidance, recovery hint, event signals |
| Judge | Evidence-linked scoring, diagnosis, compliance detection | Motivational coaching tone, future practice planning | Transcript, rubric, compliance rules, playbook, structured events | Subskill scores, diagnosis, evidence references, compliance flags |
| Coach | Teaching feedback, behavior advice, continuity plan | Rewriting historical scores, simulating the doctor, owning raw compliance policy | Judge output, learner history, progress, recommendation context | Feedback, target behavior, teaching plan, next actions |

Rules:

- Judge output must remain evidence-backed and schema-validated.
- Coach may explain and teach from Judge output, but must not silently change Judge scores.
- Director may guide the next turn, but must not become a heavy autonomous agent.
- Doctor behavior must remain scenario/persona/playbook-grounded.
- Recommendation policy should consume Judge, Coach, compliance, and progress signals without moving those responsibilities into Web or Hermes.

### Reference Review Summary

Use `docs/architecture/reference-mapping.md` as the source of truth for this review. The short version:

- Hermes-agent contributes the best patterns for central registries, command/action metadata, SQLite session search, request/session logging, doctor diagnostics, process management, prompt assembly discipline, and context compression boundaries.
- DeepTutor contributes the best patterns for Tools vs Capabilities, `UnifiedContext`, stream event envelopes, capability manifests, plugin loading, session persistence, prompt loading, setup initialization, and learning-workspace concepts.
- COSI should copy design patterns first. Direct code copy is exceptional and must be explicitly attributed.
- Hermes stays thin. DeepTutor-style capability depth belongs in domain runtimes and platform packages, not in Hermes routing or Web UI state.

### Project Structure Review

Current structure is directionally correct, but the next architecture work should make boundaries executable instead of only documented:

- `apps/mr-visit-jp-runtime/src/main.py` is already too broad for long-term change velocity. Split it into route modules, dependency boot wiring, and model/contract modules after API contract consolidation.
- `apps/hermes-orchestrator` should grow registry-based routing and diagnostics, not MR business logic.
- `apps/web` has useful Alpha flows, but large feature files should be split after payload contracts stabilize.
- `packages/*` are mostly skeletons. Turn them into real code packages only when a phase needs that boundary.
- `services/*` are currently service contract placeholders. Do not add deployable service code there until store interfaces and SQL mode are designed.
- `domains/mr_visit_jp` is the right home for scenarios, prompt profiles, rubrics, compliance rules, and future playbooks.

### Standard Verification Commands

Use focused commands while developing, then broaden before finishing high-risk work.

```bash
make bootstrap
make stack-up
make smoke-check
make stack-down

./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests
./.venv/bin/python -m pytest apps/hermes-orchestrator/tests
pnpm build
pnpm typecheck
```

When changing only docs, run enough validation to ensure referenced commands and paths still exist.

## 1. How AI Engineers Should Execute TODO Items

Each implementation task should follow this shape:

- Read the listed files first.
- Preserve the ownership boundary described in the task.
- Add or update tests at the same layer as the behavior change.
- Update docs only where user-facing or developer-facing behavior changes.
- Run the verification commands listed in the task.
- Do not broaden scope into adjacent phases unless the task explicitly says so.

If an implementation reveals that an item is wrongly ordered, update this TODO with the reason instead of silently skipping the dependency.

## 2. Immediate Execution Queue

These are the next recommended tickets in order. They are small enough for AI engineers to execute precisely and large enough to improve project momentum.

### Q0. Add Reference Adoption Guardrails

Status: [x]

Goal:
Make the Hermes-agent and DeepTutor reference policy enforceable before copying or adapting code from them.

Why:
The references are now first-class design inputs. Without a guardrail, future AI engineers may accidentally import reference code, copy large subsystems, or blur license/ownership boundaries.

Files to read:

- `docs/architecture/reference-mapping.md`
- `references/README.md`
- `references/hermes-agent/LICENSE`
- `references/deeptutor/LICENSE`
- `docs/adrs/0003-hermes-inspired-skill-registry.md`
- `docs/adrs/0004-deeptutor-inspired-capability-packaging.md`
- `TODO.md`

Implementation notes:

- Add a lightweight check that fails if runtime paths import from `references/`.
- Suggested name: `scripts/check-no-reference-imports.sh`.
- Suggested scope: `apps/`, `packages/`, `services/`, and `domains/`.
- Add an adoption log template under `docs/adrs/` or `docs/architecture/` for any future copied/adapted reference code.
- Document the minimum required fields: source repo, source path, license, copied/adapted lines or concept, reason, COSI target path, tests, and reviewer.
- Keep this as governance plus automation. Do not refactor runtime code.

Acceptance:

- A command exists to detect direct `references/` imports in runtime paths.
- README or docs explain how to record copied/adapted code.
- The check is runnable locally and suitable for CI.
- Existing runtime tests are unaffected.

Verification:

```bash
scripts/check-no-reference-imports.sh
bash -n scripts/*.sh
```

Do not:

- Vendor large reference modules.
- Turn either reference repo into a submodule.
- Change the runtime architecture while adding this guard.

### Q1. Decouple Demo Data Refresh From Runtime Boot

Status: [x]

Goal:
Make demo seeding explicit for local development while keeping runtime boot predictable for CI/staging.

Why:
Runtime currently auto-seeds demo data unless disabled. This is convenient locally but can hide startup cost and mutate data unexpectedly in cleaner environments.

Files to read:

- `apps/mr-visit-jp-runtime/src/main.py`
- `apps/mr-visit-jp-runtime/src/seed_demo_data.py`
- `apps/mr-visit-jp-runtime/src/services/demo_progress_seed.py`
- `scripts/bootstrap.sh`
- `scripts/seed-mr-visit-jp.sh`
- `README.md`

Implementation notes:

- Introduce an explicit environment mode, for example `MR_RUNTIME_DEMO_SEED_MODE=auto|manual|disabled`.
- Preserve current local convenience through `.env.example` or `bootstrap`, not hidden production defaults.
- `manual` should never seed during runtime boot.
- `auto` should seed on boot only for local/dev use.
- `disabled` should skip all demo seed behavior.
- Keep `make seed-mr-visit-jp` as the canonical manual seed command.

Acceptance:

- Runtime boot behavior is controlled by one documented setting.
- `make bootstrap` still creates usable demo data.
- `make stack-up` still leads to a usable app after bootstrap.
- Tests cover at least auto and disabled/manual boot behavior.

Verification:

```bash
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_demo_progress_seed.py apps/mr-visit-jp-runtime/tests/test_seed_demo_data_cli.py
make stack-up
make smoke-check
make stack-down
```

Do not:

- Move demo seed logic into Web or Hermes.
- Delete existing demo learners.
- Introduce a database dependency.

### Q2. Add Local Stack Regression Coverage

Status: [x]

Goal:
Make the local stack scripts safer to change by adding script-level regression checks.

Why:
`stack-up`, `stack-down`, and `smoke-check` are now core developer workflow. They should fail with actionable errors.

Files to read:

- `scripts/stack-common.sh`
- `scripts/stack-up.sh`
- `scripts/stack-down.sh`
- `scripts/stack-status.sh`
- `scripts/smoke_check.py`
- `Makefile`

Implementation notes:

- Add a lightweight shell test script under `scripts/` or Python test under an appropriate tests directory.
- Cover `.env` default loading, environment override precedence, stale PID cleanup, and port-in-use messaging.
- Keep tests local and deterministic. Do not require Docker.
- If full background process testing is too heavy for pytest, add a documented smoke command that uses temporary ports.

Acceptance:

- `bash -n` is run against all shell scripts.
- At least one automated test verifies `.env` defaults do not override explicit environment variables.
- At least one automated test verifies stale PID files are cleaned.
- Documentation tells developers how to inspect stack logs.

Verification:

```bash
bash -n scripts/*.sh
./.venv/bin/python -m pytest
```

Do not:

- Replace shell scripts with a new task runner.
- Make stack scripts depend on CI-only tooling.

### Q3. Expand Event Taxonomy And Turn Signal Coverage

Status: [x]

Goal:
Create a clearer event vocabulary for live sessions so diagnosis, review replay, recommendation, and analytics have stable signal inputs.

Why:
Events are already persisted and used, but future training quality depends on consistent event names and meanings.

Files to read:

- `apps/mr-visit-jp-runtime/src/session_engine/state_machine.py`
- `apps/mr-visit-jp-runtime/src/persistence/file_event_store.py`
- `apps/mr-visit-jp-runtime/tests/test_state_machine_heuristics.py`
- `apps/mr-visit-jp-runtime/tests/test_runtime_api.py`
- `services/event-store/README.md`

Implementation notes:

- Define a canonical event taxonomy for MR sessions.
- Add event categories such as opening, profiling, evidence, objection, compliance, closing, recovery, and completion.
- Ensure events include enough structured metadata for later replay and analytics.
- Keep event generation rule-driven for Alpha.
- Persist event versions if the payload shape changes.

Acceptance:

- Event names are documented in `services/event-store/README.md` or a domain event reference.
- State-machine tests cover the most important event transitions.
- Session event API still returns ordered events.
- Existing review/progress behavior remains stable.

Verification:

```bash
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_state_machine_heuristics.py apps/mr-visit-jp-runtime/tests/test_runtime_api.py
make smoke-check
```

Do not:

- Put event interpretation logic in Hermes.
- Make events model-only.

### Q4. Improve Director And Doctor Turn Heuristics

Status: [x]

Goal:
Make the live training session feel more like a structured MR visit and less like generic turn exchange.

Why:
Training quality is the next core product constraint. The Director/Doctor v1 is useful, but richer scenario-specific guidance will improve both learner experience and downstream review quality.

Files to read:

- `apps/mr-visit-jp-runtime/src/session_engine/state_machine.py`
- `apps/mr-visit-jp-runtime/src/services/coach_continuity.py`
- `domains/mr_visit_jp/scenarios/*.yaml`
- `domains/mr_visit_jp/assets/personas/doctor_personas.yaml`
- `apps/mr-visit-jp-runtime/tests/test_state_machine_heuristics.py`

Implementation notes:

- Add scenario-specific recovery patterns from scenario assets.
- Use persona attitude/time pressure to vary doctor pushback.
- Use continuity context to hint at the learner's next best action.
- Let Director distinguish between missing opening, weak profiling, evidence dump, unsupported claim, unresolved objection, and weak close.
- Keep the implementation deterministic and testable.

Acceptance:

- Busy-doctor scenarios push for brevity and earlier close.
- Evidence-check scenarios ask for endpoints/safety/use-case detail.
- Adverse-event scenarios prioritize reporting/compliance over promotion.
- Director recommendations are specific enough to guide the next learner turn.
- Tests cover at least three scenario/persona combinations.

Verification:

```bash
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_state_machine_heuristics.py
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_runtime_api.py
make smoke-check
```

Do not:

- Replace Director v1 with a heavy autonomous agent.
- Move doctor roleplay into Hermes.
- Add non-deterministic model calls to default mock mode.

### Q5. Add Evidence-Linked Review Details

Status: [x]

Goal:
Make review payloads trace scores and diagnosis back to specific transcript turns.

Why:
The platform promise is diagnosis, not vague summary. Learners and supervisors should see why a subskill score was assigned.

Files to read:

- `packages/evaluation-core/src/evaluation_core/mr_visit_jp.py`
- `apps/mr-visit-jp-runtime/src/evaluation/review_builder.py`
- `packages/shared-schemas/schemas/judge_review.schema.json`
- `apps/web/src/features/sessions/review-flow.tsx`
- `apps/mr-visit-jp-runtime/tests/test_transcript_fixture_evaluation.py`

Implementation notes:

- Add turn references or evidence spans to subskill evidence.
- Preserve backward compatibility for older review payloads.
- Update schemas before runtime logic.
- Update Web review display only after payload shape is validated.

Acceptance:

- Each priority subskill includes at least one evidence item tied to a turn index when turns exist.
- Review page can render evidence without breaking old payloads.
- Fixture tests assert evidence linkage.

Verification:

```bash
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_transcript_fixture_evaluation.py
pnpm build
make smoke-check
```

Do not:

- Invent evidence that is not present in the transcript.
- Let schema validation become optional.

## 3. Phase R: Reference-Inspired Architecture Foundation

Theme:
Convert the best Hermes-agent and DeepTutor ideas into COSI-native boundaries before the platform grows.

### R1. Central Skill, Capability, And Action Registry Design

Status: [x]

Reference source:
Hermes `tools/registry.py` and `hermes_cli/commands.py`; DeepTutor `runtime/registry/*`.

Goal:
Define one canonical registry model for domain skills, runtime capabilities, and externally visible actions.

Files:

- `packages/skill-registry/README.md`
- `domains/mr_visit_jp/manifests/skill.yaml`
- `apps/hermes-orchestrator/src/main.py`
- `apps/hermes-orchestrator/src/runtime_proxy.py`
- `docs/architecture/reference-mapping.md`

Tasks:

- Define registry concepts: skill, capability, action, route target, health check, required/optional contract, and UI metadata.
- Decide which metadata Web can consume and which remains backend-only.
- Define alias behavior and duplicate-name handling before implementation.
- Add a migration plan from hard-coded MR routes to registry routing.

Acceptance:

- AI engineers can implement `packages/skill-registry` without guessing the registry vocabulary.
- Hermes can remain thin while still listing and routing registered capabilities.
- The design explicitly rejects importing Hermes registry code.

### R2. Unified Domain Context

Status: [x]

Reference source:
DeepTutor `core/context.py`; Hermes session/log context patterns.

Goal:
Replace parameter drift across runtime services with a typed context object that follows a session turn through Director, Doctor, Judge, Coach, events, and persistence.

Files:

- `apps/mr-visit-jp-runtime/src/session_engine/state_machine.py`
- `apps/mr-visit-jp-runtime/src/evaluation/review_builder.py`
- `apps/mr-visit-jp-runtime/src/services/coach_continuity.py`
- `apps/mr-visit-jp-runtime/src/services/progress_tracker.py`
- `packages/shared-schemas/README.md`

Tasks:

- Define `DomainSessionContext` or equivalent with session, turn, learner, domain, scenario, persona, prompt profile, experiment, continuity, locale, and trace metadata.
- Keep it serializable or convertible into serializable persistence payloads.
- Introduce it behind existing APIs; do not break Web/Hermes payloads.
- Add tests that prove context fields reach events and review metadata.

Acceptance:

- New runtime features do not need to thread separate `learner_id`, `scenario_id`, prompt profile, and continuity params manually.
- Context contains no UI-only state and no Hermes-only routing logic.

### R3. COSI Stream/Event Envelope

Status: [x]

Reference source:
DeepTutor `core/stream.py` and `core/stream_bus.py`; Hermes trajectory/session logging.

Goal:
Create a canonical event envelope that can support current persisted events, future WebSocket streaming, replay, analytics, and model/tool traces.

Files:

- `apps/mr-visit-jp-runtime/src/persistence/file_event_store.py`
- `apps/mr-visit-jp-runtime/src/session_engine/state_machine.py`
- `services/event-store/README.md`
- `packages/shared-schemas/schemas/*.json`

Tasks:

- Define common fields: `type`, `source`, `stage`, `content`, `metadata`, `session_id`, `turn_id`, `seq`, `timestamp`, and `schema_version`.
- Map MR-specific taxonomy from Q3 into this envelope.
- Decide how old file events are read when fields are missing.
- Keep the initial implementation simple and synchronous; do not add WebSockets yet.

Acceptance:

- Event payloads can be replayed and tested without app-specific assumptions.
- Future streaming can reuse the same event shape.

### R4. Doctor Diagnostics And Stack Health

Status: [x]

Reference source:
Hermes `hermes_cli/doctor.py`, process registry, and logging setup; DeepTutor setup initializer.

Goal:
Turn local setup and stack health into a clear diagnostic surface.

Files:

- `scripts/bootstrap.sh`
- `scripts/stack-up.sh`
- `scripts/stack-status.sh`
- `scripts/smoke_check.py`
- `apps/mr-visit-jp-runtime/src/scenarios/asset_loader.py`
- `README.md`

Tasks:

- Add `make doctor` or equivalent script.
- Check Python, virtualenv, Node, pnpm, env files, ports, process IDs, domain asset validity, and service health.
- Redact secrets in output.
- Make failures actionable with exact commands or file paths.

Acceptance:

- A fresh-clone developer can diagnose failed bootstrap/stack/smoke without reading stack traces first.
- The command is safe to run repeatedly.

### R5. Session Store And Search Blueprint

Status: [x]

Reference source:
Hermes SQLite WAL/FTS session store; DeepTutor SQLite session/turn/event store.

Goal:
Design production persistence with searchability before writing SQL migrations.

Files:

- `apps/mr-visit-jp-runtime/src/persistence/*.py`
- `services/session-store/README.md`
- `services/event-store/README.md`
- `services/progress-service/README.md`
- `apps/mr-visit-jp-runtime/alembic.ini`
- `docs/architecture/session-store-search-blueprint.md`

Tasks:

- Define tables for learners, sessions, turns, events, reviews, progress snapshots, recommendations, and prompt context.
- Decide which fields should be indexed for replay, supervisor search, compliance audit, and prompt-profile QA.
- Decide whether FTS indexes transcript/review text in Phase D or after SQL mode stabilizes.
- Keep storage behind interfaces.

Acceptance:

- SQL migration work can start with a reviewed schema target.
- Search requirements do not leak into domain scoring logic.

### R6. Prompt Asset Manager

Status: [x]

Reference source:
DeepTutor prompt manager and Hermes prompt builder.

Goal:
Make prompt/profile loading deterministic, validated, localized where needed, and snapshot-testable.

Files:

- `domains/mr_visit_jp/prompts/**`
- `apps/mr-visit-jp-runtime/src/providers/model_artifact_generator.py`
- `packages/prompt-builder/README.md`
- `docs/prompts/mr-visit-jp-agent-spec.md`

Tasks:

- Define prompt asset lookup, fallback, cache invalidation, and profile version rules.
- Validate prompt assets at boot alongside scenario/rubric assets.
- Add snapshot tests for assembled prompts before moving logic into `packages/prompt-builder`.
- Keep model-provider calls separate from prompt rendering.

Acceptance:

- Prompt changes are diffable and testable.
- Invalid prompt profile data fails before a session uses it.

### R7. Session Logging, Trace IDs, And Redaction

Status: [x]

Reference source:
Hermes session-aware logging and redaction formatter; DeepTutor trace metadata.

Goal:
Make local and future production logs useful for debugging a single learner session without leaking secrets or full sensitive payloads.

Files:

- `apps/mr-visit-jp-runtime/src/main.py`
- `apps/hermes-orchestrator/src/main.py`
- `scripts/smoke_check.py`
- `services/event-store/README.md`
- `docs/architecture/data-flow.md`

Tasks:

- Define trace fields: request id, session id, turn id, learner id, domain id, prompt profile, experiment id, and service name.
- Decide which fields may appear in plain logs and which must be redacted or hashed.
- Add a shared logging guideline before introducing a shared logging package.
- Ensure smoke-check failures include enough trace context to find the matching runtime/Hermes logs.

Acceptance:

- A failed local smoke session can be traced through Web, Hermes, and runtime logs.
- Secrets and provider tokens are never printed.
- Logging changes do not alter API payloads.

## 4. Phase A: Alpha Hardening

Theme:
Make the existing single-domain Alpha reliable, inspectable, and easy to iterate before broadening scope.

### A1. API Contract Consolidation

Status: [x]

Goal:
Reduce drift between runtime Pydantic response models, Hermes proxy expectations, Web TypeScript payload assumptions, and shared schemas.

Files:

- `apps/mr-visit-jp-runtime/src/main.py`
- `apps/hermes-orchestrator/src/main.py`
- `apps/web/src/lib/runtime-api.ts`
- `packages/shared-schemas/schemas/*.json`
- `packages/shared-types/README.md`

Tasks:

- Identify all runtime API response payloads currently duplicated across layers.
- Define which contracts should live in JSON Schema, Python models, or TypeScript types.
- Add contract tests for representative payloads: scenario list, session start, turn, finish, review, progress, events, gates.
- Document compatibility rules for adding fields and changing response shapes.

Acceptance:

- Web-visible payload shape changes require either schema/type updates or explicit compatibility notes.
- Hermes proxy tests assert status code and payload preservation.
- Runtime tests validate core response payloads.

### A2. File Persistence Safety

Status: [x]

Goal:
Make local file stores safer until SQL persistence lands.

Files:

- `apps/mr-visit-jp-runtime/src/persistence/file_session_store.py`
- `apps/mr-visit-jp-runtime/src/persistence/file_event_store.py`
- `apps/mr-visit-jp-runtime/src/persistence/file_progress_store.py`
- `apps/mr-visit-jp-runtime/tests/test_runtime_api.py`

Tasks:

- Review atomic write behavior across all stores.
- Add corruption handling tests for partial/invalid JSON.
- Ensure duplicate finalization and retry behavior remain idempotent.
- Decide whether lightweight file locks are needed for local multi-process usage.

Acceptance:

- Invalid JSON does not crash unrelated sessions.
- Retry of finish/progress update remains idempotent.
- Store error messages include enough path/session context for debugging.

### A3. Observability For Local Runtime

Status: [x]

Goal:
Expose enough local observability to debug session flow without reading raw JSON files first.

Files:

- `apps/mr-visit-jp-runtime/src/main.py`
- `apps/hermes-orchestrator/src/main.py`
- `scripts/smoke_check.py`
- `scripts/stack-status.sh`

Tasks:

- Add request/session correlation IDs where useful.
- Include prompt profile, experiment id, session id, and learner id in key logs.
- Add an optional diagnostic endpoint or CLI command for local-only runtime status if needed.
- Make smoke-check failure messages identify which service failed and which URL was called.

Acceptance:

- A failed smoke check points to Web, Hermes, or runtime clearly.
- Local stack logs include enough context to trace a single smoke session.

### A4. Regression Fixture Expansion

Status: [x]

Goal:
Cover the behavior that matters most for training stability.

Files:

- `tests/transcripts/**`
- `tests/fixtures/recommendations/**`
- `apps/mr-visit-jp-runtime/tests/test_recommendation_fixtures.py`
- `apps/mr-visit-jp-runtime/tests/test_transcript_fixture_evaluation.py`

Tasks:

- Add transcript fixtures for strong opening, weak opening, evidence dump, compliant adverse-event handling, non-compliant adverse-event handling, unresolved objection, and weak close.
- Add recommendation fixtures for recurring weakness, declining trend, scenario repetition avoidance, compliance severity, and progression after improvement.
- Keep fixtures small and readable.

Acceptance:

- Fixture names explain the behavior under test.
- Review and recommendation changes can be regression-tested without running the Web app.

## 5. Phase B: Training Quality

Theme:
Improve the pedagogical value of MR training through measurable training-quality metrics, scenario playbooks, compliance-first signals, continuity-based teaching plans, and explainable practice paths.

### B0. Training Quality Metrics Definition

Status: [x]

Goal:
Define measurable training-quality signals before deepening scenario playbooks, compliance coaching, continuity plans, and recommendation policy.

Why:
The system already has a working training loop, scoring, events, review, progress, and recommendations. The next risk is improving engineering completeness without proving that learners receive clearer, more actionable, and more trustworthy training feedback.

Files to read:

- `domains/mr_visit_jp/scenarios/*.yaml`
- `domains/mr_visit_jp/rubrics/skill_model.yaml`
- `domains/mr_visit_jp/rubrics/diagnosis_types.yaml`
- `domains/mr_visit_jp/compliance/rules.yaml`
- `packages/evaluation-core/src/evaluation_core/mr_visit_jp.py`
- `apps/mr-visit-jp-runtime/src/evaluation/review_builder.py`
- `apps/mr-visit-jp-runtime/src/services/recommendation_engine.py`
- `apps/mr-visit-jp-runtime/tests/test_transcript_fixture_evaluation.py`
- `apps/mr-visit-jp-runtime/tests/test_recommendation_fixtures.py`

Tasks:

- Define training-quality dimensions for the MR loop:
  - scenario realism
  - turn guidance specificity
  - evidence quality
  - diagnosis clarity
  - compliance signal usefulness
  - coaching actionability
  - recommendation explainability
  - multi-session improvement visibility
- Add a short quality rubric for each dimension.
- Decide which dimensions can be checked by deterministic fixtures now and which require later human/SME review.
- Add fixture metadata conventions for expected training-quality signals.
- Document how these metrics should guide B1-B4 work.

Acceptance:

- TODO.md or a referenced future doc task defines what “better training quality” means in testable terms.
- Each B1-B4 task can point to at least one training-quality dimension.
- Fixture-based quality checks are separated from future human/SME evaluation.
- The roadmap no longer treats valid schema output as sufficient proof of learning value.

Verification:

```bash
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_transcript_fixture_evaluation.py apps/mr-visit-jp-runtime/tests/test_recommendation_fixtures.py
```

Do not:

- Introduce non-deterministic model judging as the default quality gate.
- Treat user delight, gamification, or UI polish as substitutes for evidence-backed learning quality.
- Move MR-specific quality rules into Hermes or Web.

### B1. Scenario-Specific Playbooks

Status: [x]

Goal:
Turn each scenario into a structured teaching asset that can guide the Doctor, Director, Judge, Coach, Review, and Recommendation policy consistently.

Why:
Current scenario data can support roleplay and scoring, but richer training behavior requires explicit teaching intent. Playbooks should make the expected visit flow, common learner failures, recovery moves, and completion signals visible as domain assets rather than hidden Python heuristics.

Files:

- `domains/mr_visit_jp/scenarios/*.yaml`
- `domains/mr_visit_jp/rubrics/skill_model.yaml`
- `domains/mr_visit_jp/rubrics/diagnosis_types.yaml`
- `apps/mr-visit-jp-runtime/src/scenarios/asset_loader.py`

Tasks:

- Extend scenario schema with a `playbook` object.
- Include at least these playbook fields:
  - `learning_objective`
  - `target_subskills`
  - `expected_flow`
  - `key_discovery_questions`
  - `acceptable_evidence_moves`
  - `common_failure_patterns`
  - `recovery_moves`
  - `completion_signals`
  - `positive_example_moves`
  - `negative_example_moves`
- Keep playbook data under `domains/mr_visit_jp/scenarios/*.yaml` or a domain-owned asset file referenced by scenarios.
- Validate playbook fields at boot.
- Add scenario asset quality checks:
  - every scenario has one learning objective
  - every scenario maps to at least two target subskills
  - every scenario has at least three common failure patterns
  - compliance-sensitive scenarios include compliance-specific recovery or escalation moves
  - every scenario has at least one positive and one negative example move
- Use playbook fields in Director/Doctor heuristics only after validation and tests are added.
- Prepare Judge/Coach usage, but do not force all components to consume every playbook field in the first implementation.

Acceptance:

- All 8 scenarios include minimal but meaningful playbook data.
- Invalid playbook data fails boot with a clear asset error.
- Director/Doctor tests prove at least three scenario-specific playbook fields affect deterministic behavior.
- Playbook assets can explain the intended learning objective, expected learner behavior, common failure patterns, and recovery moves without reading Python code.

Do not:

- Encode these playbooks in Python constants if they belong to domain assets.
- Do not create generic platform playbook abstractions until a second domain proves which fields are shared.
- Do not hide scenario teaching intent inside state-machine heuristics.
- Do not require model calls to interpret playbooks in default mock mode.

### B2. Compliance As First-Class Training Signal

Status: [x]

Goal:
Make compliance a first-class training signal that runs alongside skill scoring, affects coaching and recommendation priority, and remains clearly visible without replacing subskill evaluation.

Why:
In MR training, a learner can communicate well while still creating compliance risk, or handle a compliance-sensitive situation correctly even if other skills are weak. Skill feedback and compliance feedback must be separated but coordinated.

Files:

- `domains/mr_visit_jp/compliance/rules.yaml`
- `packages/evaluation-core/src/evaluation_core/mr_visit_jp.py`
- `apps/mr-visit-jp-runtime/src/services/recommendation_engine.py`
- `apps/web/src/features/sessions/review-flow.tsx`

Tasks:

- Define two review channels:
  - Skill Channel: subskill scores, behavior diagnosis, coaching actions.
  - Compliance Channel: risk type, severity, evidence, required handling, remedial priority.
- Define severity handling for:
  - compliant caution
  - risky overclaim
  - unsupported claim
  - missing adverse-event reporting
  - off-label implication
  - failure to recover after a compliance risk
- Ensure compliance flags do not replace subskill scoring.
- Add positive compliance evidence, not only negative risk flags.
- Recommend remedial scenarios when compliance severity is high or repeated.
- Add recommendation rules:
  - severe compliance risk outranks ordinary subskill weakness
  - repeated medium compliance risk triggers remedial path
  - correct compliance handling can reduce remedial priority but should still be recorded
- Surface compliance flags clearly in review without making the UI punitive or vague.

Acceptance:

- Compliance regression fixtures prove severe flags affect recommendation priority.
- Review page separates skill feedback from compliance signal.
- Correct compliance handling can appear as positive evidence.
- Recommendation explanations identify whether compliance, skill weakness, or both drove the next practice path.

Do not:

- Collapse compliance severity into the overall score without explanation.
- Hide compliance findings inside generic coaching text.
- Let Web define compliance interpretation logic.
- Treat compliance only as a punishment signal; correct handling should also be recognized.

### B3. Coaching Continuity As A Teaching Plan

Status: [x]

Goal:
Make continuity more than memory display; it should actively guide the next session and review.

Files:

- `apps/mr-visit-jp-runtime/src/services/coach_continuity.py`
- `apps/mr-visit-jp-runtime/src/services/progress_tracker.py`
- `apps/web/src/features/scenarios/scenarios-flow.tsx`
- `apps/web/src/features/sessions/session-flow.tsx`
- `apps/web/src/features/sessions/progress-flow.tsx`

Tasks:

- Persist a small teaching plan: focus, reason, prior evidence, next target behavior, and success criterion.
- Store a teaching plan version or snapshot id on session start.
- Freeze the plan at session start so later progress changes do not rewrite the session's target.
- Include source evidence from previous sessions when available.
- Define success criterion in observable behavior terms, not vague improvement language.
- Show the plan in scenario/session context.
- Compare the finalized review against the frozen plan:
  - achieved
  - partially achieved
  - not achieved
  - not observable
- Feed the result back into learner memory and recommendation policy.

Acceptance:

- Starting a recommended scenario includes a continuity brief tied to prior learner history.
- The teaching plan is frozen at session start and visible in session/review metadata.
- Review explains whether the target behavior improved using transcript evidence.
- Tests cover memory carry-over after at least two finalized sessions.
- Recommendation policy can use teaching-plan outcome when ranking the next practice path.

Do not:

- Let the active teaching plan mutate after a session has started.
- Store vague goals such as “improve communication” without observable success criteria.
- Display memory without turning it into a next-session behavior target.

### B4. Recommendation Policy V2

Status: [x]

Goal:
Turn recommendation from a single next scenario into a short, explainable practice path that connects learner history, transcript evidence, target subskills, compliance priority, and stop conditions.

Files:

- `apps/mr-visit-jp-runtime/src/services/recommendation_engine.py`
- `apps/mr-visit-jp-runtime/src/services/progress_tracker.py`
- `apps/web/src/features/sessions/progress-flow.tsx`
- `tests/fixtures/recommendations/**`

Tasks:

- Return ranked practice path entries, not just independent recommendations.
- Each practice path entry should include:
  - scenario id
  - target subskills
  - reason
  - evidence source
  - expected difficulty
  - suggested repetition count
  - stop condition
  - whether the reason is skill, compliance, continuity, curriculum, or mixed
- Avoid recommending the same scenario repeatedly unless there is a clear remediation reason.
- Add explanation fields that can be rendered directly in Progress UX.
- Preserve current payload compatibility or version the response.
- Add fixture cases for:
  - recurring weakness
  - declining trend
  - recent improvement
  - severe compliance risk
  - repeated medium compliance risk
  - scenario repetition avoidance
  - teaching-plan achieved vs not achieved

Acceptance:

- Progress page can show a 2-3 step practice path.
- Recommendation fixture tests cover ranking, explanation, repetition avoidance, compliance priority, and stop conditions.
- Each recommendation can answer:
  - why this scenario
  - why now
  - what to practice
  - what evidence triggered it
  - when to stop repeating it

Do not:

- Return opaque recommendations that cannot be explained from learner history, review evidence, compliance rules, or curriculum state.
- Recommend the same scenario indefinitely after improvement.
- Move recommendation ranking rules into Web.

## 6. Phase C: Product UX And Learning Experience

Theme:
Make the Web app feel like a training product people can use repeatedly, not only a backend demo surface.

### C1. Live Session UX Upgrade

Status: [x]

Goal:
Improve the live training flow for repeated practice.

Files:

- `apps/web/src/features/sessions/session-flow.tsx`
- `apps/web/src/lib/runtime-api.ts`
- `apps/web/src/app/sessions/[id]/page.tsx`

Tasks:

- Show scenario goal, doctor persona, continuity focus, and current Director guidance in a compact training layout.
- Add clear states for loading, turn submission, finish in progress, finalized, and failed requests.
- Prevent duplicate turn submission and duplicate finish clicks.
- Preserve session state across refresh.

Acceptance:

- A learner can refresh during an active session and continue.
- UI prevents accidental duplicate turn/finish actions.
- Mobile layout remains usable.

Verification:

```bash
pnpm build
pnpm typecheck
make smoke-check
```

### C2a. Minimal Evidence Review UX

Status: [x]

Goal:
Make the review page immediately useful to learners by clearly showing what happened, why it was diagnosed that way, and what to practice next.

Why:
Evidence-linked review only creates product value when learners can understand it without opening raw JSON or reading developer logs. The first review UX upgrade should prioritize clarity over advanced replay.

Files:

- `apps/web/src/features/sessions/review-flow.tsx`
- `apps/web/src/app/records/[id]/review/page.tsx`
- `apps/web/src/app/sessions/[id]/review/page.tsx`
- `apps/web/src/lib/runtime-api.ts`

Tasks:

- Show overall band, priority subskills, diagnosis, transcript evidence, coaching next actions, compliance channel, and next recommendation.
- Render evidence turn references when available.
- Add graceful fallback for older reviews without evidence refs.
- Separate Skill Channel and Compliance Channel visually.
- Make the next practice action obvious.
- Avoid requiring replay or advanced filtering for the first version.

Acceptance:

- Review can be understood without opening raw JSON.
- Learner can identify one or two concrete behaviors to improve.
- Compliance signals are visible but not mixed into generic skill feedback.
- Old review payloads still render gracefully.

Verification:

```bash
pnpm build
pnpm typecheck
make smoke-check
```

### C2b. Advanced Transcript Linking And Replay

Status: [x]

Goal:
Add richer transcript navigation and replay once the minimal evidence review is stable.

Files:

- `apps/web/src/features/sessions/review-flow.tsx`
- `apps/web/src/features/sessions/records-flow.tsx`
- `apps/web/src/app/records/[id]/page.tsx`
- `apps/web/src/app/records/[id]/review/page.tsx`

Tasks:

- Link evidence items to transcript turns.
- Highlight event markers in the transcript.
- Add replay-friendly grouping by opening, profiling, evidence, objection, compliance, closing, recovery, and completion.
- Preserve backward compatibility for older sessions and reviews.
- Coordinate with C4 records filtering instead of duplicating filter state.

Acceptance:

- A reviewer can jump from a score or diagnosis to the exact transcript evidence.
- Replay shows event markers without changing the original transcript.
- Older reviews without event/evidence metadata remain readable.

Verification:

```bash
pnpm build
pnpm typecheck
make smoke-check
```

### C3. Progress UX As Training Plan

Status: [x]

Goal:
Turn progress page into the learner's next practice dashboard.

Files:

- `apps/web/src/features/sessions/progress-flow.tsx`
- `apps/web/src/app/progress/page.tsx`

Tasks:

- Show current level, total sessions, subskill trends, recurring weakness clusters, recent history, coach memory, and practice path.
- Add learner id switcher for demo learners and local testing.
- Make recommendation reasons concise and specific.

Acceptance:

- Demo learners with 100/300/1000 sessions show meaningfully different histories.
- Starting a recommended scenario is one click.

### C4. Records And Replay

Status: [x]

Goal:
Make historical sessions useful for review and QA.

Files:

- `apps/web/src/features/sessions/records-flow.tsx`
- `apps/web/src/features/sessions/review-flow.tsx`
- `apps/web/src/app/records/[id]/page.tsx`

Tasks:

- Add filters for scenario, score band, priority subskill, compliance severity, finish reason, and prompt profile.
- Preserve filters in URL.
- Add transcript replay with event markers.
- Add empty/error states.

Acceptance:

- A reviewer can find sessions by weakness/compliance/prompt profile.
- Shared URLs preserve filter context.

## 7. Phase D: Production Persistence Backbone

Theme:
Move from local file persistence to production-grade storage without changing domain ownership boundaries.

### D0. Persistence Behavior Contract

Status: [x]

Goal:
Define persistence behavior semantics before formalizing store interfaces or adding SQL-backed storage.

Why:
SQL schema should encode product and runtime semantics, not accidentally freeze current file-store implementation details. File mode and SQL mode must agree on session, turn, event, review, progress, and recommendation behavior.

Files:

- `apps/mr-visit-jp-runtime/src/persistence/*.py`
- `apps/mr-visit-jp-runtime/src/main.py`
- `apps/mr-visit-jp-runtime/src/evaluation/review_builder.py`
- `apps/mr-visit-jp-runtime/src/services/progress_tracker.py`
- `apps/mr-visit-jp-runtime/src/services/recommendation_engine.py`
- `services/session-store/README.md`
- `services/event-store/README.md`
- `services/progress-service/README.md`
- `docs/architecture/session-store-search-blueprint.md`

Tasks:

- Define behavior rules for:
  - session creation
  - active session lookup
  - turn append
  - duplicate turn submission
  - session finalization
  - duplicate finish retry
  - event sequence ordering
  - review generation and regeneration
  - review versioning
  - progress snapshot update
  - recommendation persistence vs recomputation
  - prompt context snapshotting
- Decide which artifacts are append-only and which are mutable.
- Define idempotency rules for finish, review, progress update, and migration import.
- Define how old/corrupt/missing artifacts are handled in file mode and SQL mode.
- Define contract tests that can later run against file store, SQL store, and fake/in-memory store.

Acceptance:

- Store interface work can implement a behavior contract rather than guessing semantics.
- SQL schema design has explicit answers for review versioning, event ordering, prompt context, and progress snapshots.
- File mode and future SQL mode can be tested with shared contract fixtures.
- No domain scoring or recommendation logic is moved into SQL as part of this contract.

Do not:

- Add SQL migrations in this task.
- Redesign public API payloads unless a behavior contract requires a versioned compatibility note.
- Hide behavior differences between file and SQL modes.

### D1. Store Interface Formalization

Status: [x]

Goal:
Define explicit store protocols before adding SQL. This task must follow D0. Store protocols should encode the persistence behavior contract instead of only matching current file-store method shapes.

Files:

- `apps/mr-visit-jp-runtime/src/persistence/*.py`
- `services/session-store/README.md`
- `services/event-store/README.md`
- `services/progress-service/README.md`

Tasks:

- Define interfaces/protocols for session, event, and progress stores.
- Convert D0 behavior rules into store protocol method contracts.
- Add shared contract-test fixtures that can be reused for file, fake/in-memory, and SQL stores.
- Keep file stores as one implementation.
- Make runtime receive store implementations from boot configuration.

Acceptance:

- Runtime tests can run against file store and a fake/in-memory store if useful.
- No route handler writes persistence directly.

### D2. SQLModel Schema And Alembic Migrations

Status: [x]

Goal:
Add SQL-backed persistence for sessions, events, progress snapshots, reviews, recommendations, and prompt context. This task must follow D0 and D1. SQL tables and migrations should implement the agreed store behavior contract and interfaces.

Files:

- `apps/mr-visit-jp-runtime/alembic.ini`
- `apps/mr-visit-jp-runtime/src/persistence/`
- `apps/mr-visit-jp-runtime/pyproject.toml`
- `docker-compose.yml`

Tasks:

- Design tables for learners, sessions, turns, events, reviews, progress snapshots, and recommendations.
- Store review versions or regeneration metadata according to D0.
- Store prompt context snapshots for auditability.
- Preserve event sequence ordering and idempotent finalization semantics.
- Run shared store contract tests in SQL mode.
- Add Alembic migration.
- Support `MR_RUNTIME_STORE_MODE=file|sql`.
- Keep file mode default until SQL tests and migration tooling are stable.

Acceptance:

- SQL mode passes runtime API tests.
- File mode remains supported.
- Migrations can create a fresh local database.

Do not:

- Move progress/recommendation logic into SQL queries prematurely.

### D3. File-To-SQL Migration Tool

Status: [x]

Goal:
Import existing `.data` artifacts into SQL for local/staging continuity.

Files:

- `apps/mr-visit-jp-runtime/src/persistence/`
- `scripts/`

Tasks:

- Add dry-run and apply modes.
- Validate JSON artifacts before import.
- Preserve session ids, learner ids, timestamps, prompt context, events, and reviews.
- Report skipped/invalid artifacts.

Acceptance:

- Demo data can be seeded in file mode, migrated to SQL, then read in SQL mode.

## 8. Phase E: Platformization And Multi-Domain Readiness

Theme:
Extract the parts that are truly platform-wide while keeping domain logic in domain runtimes.

### E1. Skill Registry Implementation

Status: [x]

Goal:
Turn `packages/skill-registry` from direction doc into usable package.

Files:

- `packages/skill-registry/README.md`
- `domains/mr_visit_jp/manifests/skill.yaml`
- `apps/hermes-orchestrator/src/main.py`

Tasks:

- Define skill manifest schema and validation.
- Register `mr_visit_jp` with base URL, supported actions, domain metadata, and health check.
- Make Hermes route through registry instead of hard-coded primary skill constants.
- Preserve current `/v1/scenarios` compatibility for the primary skill.

Acceptance:

- Hermes can list registered skills with metadata.
- Unknown skill errors remain clear.
- Contract tests cover registry routing.

### E2. Runtime Contract Spec

Status: [x]

Goal:
Document and test the minimum API contract every domain runtime must expose.

Files:

- `docs/api/hermes-orchestrator-api.md`
- `docs/api/mr-visit-jp-runtime-api.md`
- `packages/shared-schemas/`
- `apps/hermes-orchestrator/tests/test_runtime_proxy_contract.py`

Tasks:

- Define required actions: list scenarios, start, get session, turn, finish, review, events, progress, health.
- Define optional actions: evaluation gates, curriculum, organization reports.
- Add contract fixture tests that could be reused for future runtimes.

Acceptance:

- A future runtime can be implemented by following the spec without reading MR internals.

### E3. Second Domain Spike

Status: [x]

Goal:
Prove the multi-domain architecture with a tiny second training domain.

Why:
The first domain can make MR-specific concepts look platform-generic. A deliberately small but meaningfully different second domain is needed to prove which abstractions belong in shared packages and which should remain domain-owned.

Important:
This is an architecture spike, not a full second product.

Current state:
`domains/gp_visit_jp` now ships a small but fully registered spike bundle with 2
scenarios, minimal prompt assets, and domain-owned subskills. It is backed by
`apps/gp-visit-jp-runtime`, passes the shared runtime contract tests, and is
documented in `docs/architecture/second-domain-spike-review.md`.

Tasks:

- Choose a small text-only domain with 2 scenarios and 2-3 subskills.
- Prefer a domain that is conversation-based but structurally different from MR, such as customer complaint handling, internal IT helpdesk communication, sales cold call practice, or interview questioning practice.
- Package it with manifest, scenarios, rubrics, prompts, and compliance/policy if relevant.
- Keep the spike intentionally small:
  - 2 scenarios
  - 2-3 subskills
  - minimal personas
  - minimal rubric
  - minimal prompt assets
  - optional policy/compliance only if relevant
- Implement runtime only as far as needed to satisfy the domain contract.
- Register it through skill registry.
- Record which platform assumptions held and which were MR-specific.
- Identify shared package changes only after the spike is running.
- Add a short spike review document or TODO subsection summarizing required platform changes.

Acceptance:

- Web/Hermes can list multiple skills.
- `mr_visit_jp` behavior remains unchanged.
- The second domain satisfies the minimum runtime contract without copying MR internals.
- The spike produces a written list of proven shared abstractions and rejected premature abstractions.

Do not:

- Generalize everything before the spike proves the need.
- Generalize MR-specific scoring, compliance, or visit-flow concepts before the second domain proves they are shared.
- Build a full second product.
- Add thick shared packages just to make the spike look elegant.
- Let the second domain contaminate MR-specific runtime code.

## 9. Phase F: Accounts, Organizations, And Operations

Theme:
Move from local single-user Alpha to real learner/team usage.

### F1. Identity And Learner Ownership

Status: [x]

Goal:
Introduce users and learners without breaking local demo mode.

Tasks:

- Define user, learner, organization, role, and membership models.
- Decide local dev auth strategy.
- Ensure learner progress belongs to a learner under an organization when auth is enabled.
- Keep demo learners available for local development.

Acceptance:

- Auth-disabled local mode still works.
- Auth-enabled mode prevents cross-learner data access.

### F2. Team And Supervisor Views

Status: [x]

Goal:
Let supervisors inspect aggregate training progress without owning domain logic.

Tasks:

- Add team progress summaries: total sessions, average score, recurring weaknesses, compliance risk, practice completion.
- Add drill-down from team to learner to session review.
- Keep analytics read models separate from training runtime mutation logic.

Acceptance:

- Supervisor can identify who needs help and why.
- No private raw transcript is exposed unless role policy allows it.

### F3. Admin And Content Operations

Status: [x]

Goal:
Support operational management of scenarios, prompt profiles, and evaluation gates.

Tasks:

- Provide read-only admin views first.
- Show active prompt profile, gate decision, contract versions, fixture pass rates, online metrics.
- Add content validation command for domain assets.
- Add promotion workflow only after read-only visibility is stable.

Acceptance:

- Operators can understand whether a prompt profile is blocked or promoted.
- Domain asset errors can be diagnosed without reading stack traces.

## 10. Phase G: Curriculum, Practice Paths, And Skill World

Theme:
Turn repeated scenarios into an intentional learning journey.

### G1. Curriculum Model

Status: [x]

Goal:
Define domain-specific curricula that group scenarios into stages.

Tasks:

- Add curriculum assets under `domains/mr_visit_jp`.
- Define modules, prerequisites, target subskills, completion criteria, and recommended repetition.
- Connect recommendation engine to curriculum stage.

Acceptance:

- Learner progress can say which stage the learner is in and why.
- Recommendations respect both weakness and curriculum stage.

### G2. Mastery And Review Scheduling

Status: [x]

Goal:
Define when a learner has improved, mastered, or should revisit a skill.

Tasks:

- Add mastery thresholds using rolling averages and recent evidence.
- Add spaced repetition or revisit logic for decaying skills.
- Distinguish "needs practice", "improving", "stable", and "mastered".

Acceptance:

- Progress page shows actionable stage status.
- Recommendation avoids endless repetition after improvement.

### G3. World Map And Motivation Layer

Status: [x]

Goal:
Add world-building only after diagnosis/progression logic is strong.

Tasks:

- Design skill map from curriculum state.
- Add achievements only when tied to real learning behavior.
- Avoid leaderboard mechanics until organization/privacy rules are clear.

Acceptance:

- World UI reflects actual training state, not decorative progress.

## 11. Phase H: Model Ops And Prompt System

Theme:
Make model-assisted behavior safe, measurable, and replaceable.

### H1. Prompt Builder Package

Status: [x]

Why:
R6 proved prompt asset loading, profile rules, and snapshot discipline inside the MR runtime.
The next step is to turn that logic into a reusable package boundary so future runtimes can
share deterministic prompt assembly without inheriting MR-specific provider code.

Goal:
Turn `packages/prompt-builder` into shared prompt assembly utilities.

Files to read:

- `packages/prompt-builder/README.md`
- `apps/mr-visit-jp-runtime/src/providers/prompt_assets.py`
- `apps/mr-visit-jp-runtime/src/providers/prompt_renderer.py`
- `apps/mr-visit-jp-runtime/src/providers/model_artifact_generator.py`
- `domains/mr_visit_jp/prompts/**`
- `tests/fixtures/prompt_snapshots/*.json`

Implementation notes:

- Move prompt asset loading, profile override validation, prompt-context summarization, and deterministic rendering into `packages/prompt-builder`.
- Keep runtime wrappers thin so existing MR runtime call sites do not need a broad refactor.
- Preserve domain ownership boundaries:
  - prompt assets still live under `domains/`
  - runtime still chooses env vars and model-provider transport
  - prompt-builder stays side-effect free and does not make network calls
- Keep OpenAI-compatible request rendering in the package, but do not move provider retries or parsing there.
- Add package-level tests for cache invalidation, version-bump enforcement, and rendered-prompt snapshots.
- Update bootstrap/tooling so the local stack installs and detects the new package.

Acceptance:

- Runtime no longer owns the main prompt asset/version/render implementation directly.
- Prompt asset loading and rendered request payloads are testable from `packages/prompt-builder`.
- Snapshot tests still catch prompt drift for MR review artifacts.
- Local bootstrap installs the package and stack preflight detects when it is missing.

Verification:

```bash
./.venv/bin/python -m pytest packages/prompt-builder/tests apps/mr-visit-jp-runtime/tests/test_prompt_assets.py apps/mr-visit-jp-runtime/tests/test_openai_compat_provider.py
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_runtime_api.py
```

Do not:

- Move domain prompt assets out of `domains/mr_visit_jp/prompts`.
- Move model transport, retry, or fallback policy into prompt-builder.
- Broaden this package into a runtime-specific orchestration layer.


### H2. OpenAI-Compatible Provider Hardening

Status: [x]

Why:
Prompt contracts are now versioned and shared, but real-model experiments are still only as safe
as the provider edge. Runtime must survive refusals, malformed responses, and retryable provider
failures without hiding what happened in review metadata.

Goal:
Make real model mode reliable enough for controlled experiments.

Files:

- `apps/mr-visit-jp-runtime/src/providers/model_artifact_generator.py`
- `domains/mr_visit_jp/prompts/**`
- `apps/mr-visit-jp-runtime/tests/test_openai_compat_provider.py`
- `apps/mr-visit-jp-runtime/tests/test_runtime_api.py`
- `packages/evaluation-core/src/evaluation_core/mr_visit_jp.py`

Implementation notes:

- Add configurable timeout and retry settings for `openai_compat` mode.
- Treat retryable HTTP/network failures separately from parse/contract failures, and return structured provider metadata with failure stage, retry count, and fallback target.
- Detect refusal-like provider outputs explicitly before review assembly.
- Preserve partial artifact payloads so review assembly can accept valid fragments and fall back only where needed.
- Record artifact mode in review metadata so `model`, `mock`, and `rule` outcomes are distinguishable without breaking existing `artifact_sources` semantics.
- Keep fallback at runtime/evaluation boundaries; do not move it into Web or Hermes.

Acceptance:

- Model failures do not break session finalization.
- Review metadata explains whether model, mock, or rule fallback produced artifacts.

Verification:

```bash
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_openai_compat_provider.py apps/mr-visit-jp-runtime/tests/test_runtime_api.py
```

Do not:

- Treat provider refusal as a hard runtime crash.
- Hide retry/failure details behind an unstructured exception string only.
- Reclassify mock-generated artifacts as rule fallback.

### H3. Evaluation Dataset Lifecycle

Status: [x]

Why:
Prompt profiles and evaluation rules now gate rollout, but the transcript fixtures were still
treated as loose test inputs. H3 turns them into a named offline dataset with schema rules,
coverage reporting, and a repeatable local evaluation command.

Goal:
Treat prompt/evaluation fixtures as a growing quality dataset.

Files:

- `apps/mr-visit-jp-runtime/src/services/evaluation_fixture_dataset.py`
- `apps/mr-visit-jp-runtime/src/services/evaluation_gate_service.py`
- `apps/mr-visit-jp-runtime/src/offline_evaluation_report.py`
- `apps/mr-visit-jp-runtime/tests/test_transcript_fixture_evaluation.py`
- `apps/mr-visit-jp-runtime/tests/test_evaluation_gate_service.py`
- `apps/mr-visit-jp-runtime/tests/test_runtime_api.py`
- `apps/mr-visit-jp-runtime/tests/test_offline_evaluation_report.py`
- `tests/transcripts/**`
- `tests/transcripts/README.md`

Implementation notes:

- Define a fixture dataset schema with required metadata, allowed buckets, and normalized path/name validation.
- Move transcript fixtures under bucketed directories so discovery can treat the dataset as inventory instead of a hardcoded list.
- Track coverage across scenario ids, focused subskills, compliance cases, and finish reasons in the runtime gate report.
- Make offline gate execution consume the full fixture dataset dynamically and evaluate continuity fixtures with their carryover context.
- Add a repo-root command for local offline evaluation that prints dataset coverage gaps and prompt-profile deltas.
- Keep the runtime API response schema in sync so Hermes and local tooling can inspect dataset health without reading test files directly.

Acceptance:

- Adding a prompt profile requires passing fixture gates.
- Coverage gaps are visible.

Verification:

```bash
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_transcript_fixture_evaluation.py apps/mr-visit-jp-runtime/tests/test_evaluation_gate_service.py apps/mr-visit-jp-runtime/tests/test_offline_evaluation_report.py apps/mr-visit-jp-runtime/tests/test_runtime_api.py apps/mr-visit-jp-runtime/tests/test_api_response_contracts.py
make evaluate-mr-visit-jp-fixtures FORMAT=json
```

Do not:

- Leave fixture discovery hardcoded to a short allowlist.
- Add prompt-profile gating that ignores continuity/compliance fixture context.
- Treat transcript fixtures as undocumented one-off tests with no metadata contract.

H3.1 (2026-04-29) Multilingual Runtime Reply + Dataset Expansion:

- [x] Session start now accepts `locale` (`ja/zh/en` normalized at runtime boundary).
- [x] Doctor reply heuristics now render locale-aware responses for Japanese/Chinese/English.
- [x] Web start-session entries now pass UI language to runtime.
- [x] Added 30 transcript fixtures (`tests/transcripts/**`) covering:
  multilingual utterances, all buckets, all finish reasons, all compliance-case labels,
  continuity carryover patterns, and `preparation` subskill coverage.

H3.2 Next tightening pass:

- [x] Raise assertion strictness for the new fixture batch (currently broad score bands to prioritize coverage).
- [x] Add fixture-quality lint checks for duplicate message patterns and low-information turns.

### H4. Human Evaluation Feedback Loop

Status: [x]

Goal:
Create a path for trainer or SME review corrections to improve evaluation fixtures, prompt profiles, and model/rule quality over time.

Why:
AI-generated judging and coaching should be schema-validated and evidence-backed, but real MR training quality eventually needs human expert calibration. SME corrections can become high-value evaluation data instead of one-off comments.

Files:

- `apps/mr-visit-jp-runtime/src/services/human_review_feedback.py`
- `apps/mr-visit-jp-runtime/src/main.py`
- `apps/mr-visit-jp-runtime/tests/test_human_review_feedback_service.py`
- `apps/mr-visit-jp-runtime/tests/test_runtime_api.py`
- `apps/mr-visit-jp-runtime/README.md`

Implementation notes:

- Add an append-only human review feedback store with explicit `record_id` + `version` chain so corrections are versioned instead of in-place overwritten.
- Define structured correction payloads for:
  - accept AI review vs corrected review verdicts
  - subskill score overrides
  - diagnosis add/remove ids
  - compliance severity overrides
  - evidence sufficiency flags
  - SME comment
- Add fixture-promotion intent inside each feedback record and generate draft fixture candidates aligned with transcript fixture schema.
- Add local API endpoints for create/list/export/import/candidate-preview so feedback can be moved between environments and reviewed before fixture promotion.
- Keep this local-only (`/_local/*`) and do not introduce production reviewer identity/permission workflow yet.

Acceptance:

- The roadmap explains how human trainer feedback can become evaluation data.
- SME correction does not silently mutate historical AI review without versioning.
- Future offline evaluation can compare AI output against SME gold labels.

Verification:

```bash
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_human_review_feedback_service.py apps/mr-visit-jp-runtime/tests/test_export_human_review_fixture_candidates_cli.py apps/mr-visit-jp-runtime/tests/test_runtime_api.py apps/mr-visit-jp-runtime/tests/test_api_response_contracts.py apps/mr-visit-jp-runtime/tests/test_offline_evaluation_report.py
make export-human-review-fixture-candidates
```

Do not:

- Treat SME override as required for local Alpha.
- Add human review workflow before identity, roles, and review persistence are ready.
- Let human correction overwrite original AI artifacts without audit/version metadata.

## 12. Phase I: Voice And Multimodal Training

Theme:
Extend modality only after text diagnosis and progression are stable.

### I1. Voice Architecture Spike

Status: [x]

Goal:
Determine how real-time voice should integrate with session state.

Tasks:

- Decide STT/TTS provider abstraction.
- Add turn timestamps and audio artifact references to session model.
- Define latency and interruption behavior.
- Keep text session path fully functional.

Acceptance:

- A voice spike can run one scenario without changing scoring semantics.

### I2. Voice Review Signals

Status: [x]

Goal:
Use voice-specific signals only when they improve training value.

Tasks:

- Identify useful voice metrics: pacing, hesitation, interruption recovery, clarity.
- Decide whether these are MR subskills or separate communication signals.
- Add schema extensions before UI display.

Acceptance:

- Voice metrics do not pollute existing text-only subskill scoring.

## 13. Phase J: Release, Deployment, And Reliability

Theme:
Make the system deployable and operable beyond a local workstation.

### J1. App Dockerization

Status: [x]

Goal:
Containerize Web, Hermes, and runtime in addition to Postgres/Redis.

Tasks:

- Add Dockerfiles for `apps/web`, `apps/hermes-orchestrator`, and `apps/mr-visit-jp-runtime`.
- Extend `docker-compose.yml` for full local stack.
- Keep `make stack-up` useful for fast local development.

Acceptance:

- Docker compose can run the full stack from a clean clone.
- Local script stack remains faster for day-to-day development.

### J2. CI Pipeline

Status: [x]

Goal:
Run consistent checks on every change.

Tasks:

- Add jobs for Python tests, Hermes contract tests, Web build/typecheck, shell syntax checks, and smoke check where feasible.
- Cache pnpm and pip dependencies.
- Keep references excluded.

Acceptance:

- CI catches broken API contracts and broken frontend builds before merge.

### J3. Deployment Configuration

Status: [x]

Goal:
Make environment-specific config explicit.

Tasks:

- Document required environment variables for dev, staging, and production.
- Separate secrets from non-secret config.
- Add readiness and liveness endpoints if deployment target needs them.
- Add backup/restore plan for SQL mode before production data.

Acceptance:

- A new engineer can deploy staging by following docs without guessing config.

## 14. Explicit Non-Goals Until Prerequisites Land

Do not start these until their prerequisite phases are complete.

- Do not add voice/video before text review evidence, event taxonomy, and persistence contracts are stable.
- Do not add rankings/leaderboards before account, organization, privacy, and role boundaries are defined.
- Do not build a heavy autonomous Hermes agent before multi-domain routing requirements prove the need.
- Do not build a large second domain before skill registry and runtime contract are clear.
- Do not move domain rules into Web for faster display.
- Do not treat generated model feedback as authoritative without schema validation and fallback behavior.

## 15. Acceptance Review 2026-04-30

This section records the current acceptance pass against TODO.md and the actual repository state. It is intentionally written as an execution artifact so the next AI engineer can continue from verified facts rather than roadmap assumptions.

### AR1. Acceptance Execution Record

Status: [x]

Goal:
Validate the current Alpha against its documented runtime, platform, Web, content, and evaluation contracts.

Scope:

- `TODO.md`
- `README.md`
- `apps/mr-visit-jp-runtime`
- `apps/gp-visit-jp-runtime`
- `apps/hermes-orchestrator`
- `apps/web`
- `domains/mr_visit_jp`
- `domains/gp_visit_jp`
- `packages/shared-schemas`
- `packages/prompt-builder`
- `packages/evaluation-core`
- `tests/transcripts`
- `scripts`

Verification run:

```bash
scripts/check-no-reference-imports.sh
bash -n scripts/*.sh
make validate-content
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests apps/hermes-orchestrator/tests apps/gp-visit-jp-runtime/tests tests/integration packages/prompt-builder/tests packages/evaluation-core/tests
make evaluate-mr-visit-jp-fixtures FORMAT=json
pnpm typecheck
pnpm build
WEB_PORT=3300 HERMES_PORT=8400 MR_RUNTIME_PORT=8410 GP_RUNTIME_PORT=8420 STACK_STATE_DIR=.tmp/acceptance-stack make stack-up
WEB_PORT=3300 HERMES_API_BASE=http://127.0.0.1:8400 MR_VISIT_JP_RUNTIME_BASE=http://127.0.0.1:8410 GP_VISIT_JP_RUNTIME_BASE=http://127.0.0.1:8420 make smoke-check
WEB_PORT=3300 HERMES_PORT=8400 MR_RUNTIME_PORT=8410 GP_RUNTIME_PORT=8420 STACK_STATE_DIR=.tmp/acceptance-stack make stack-down
```

Results:

- Reference import guard passes.
- Shell syntax checks pass.
- Domain content validation passes for 8 MR scenarios, 7 MR subskills, 2 prompt profiles, and evaluation gates.
- Python test suite passes: 241 tests.
- Focused runtime contract retest passes: 47 tests across GP runtime, Hermes proxy, MR API response contracts, and MR runtime API.
- MR offline evaluation gate passes with 44 transcript fixtures.
- Offline dataset coverage has no missing MR scenarios, subskills, compliance-case labels, or finish reasons.
- Web TypeScript typecheck passes.
- Web production build passes.
- End-to-end local smoke passes through Web, Hermes, MR runtime, and GP runtime using alternate ports.

Fixes made during acceptance:

- `apps/gp-visit-jp-runtime/src/main.py` now returns `offline_dataset` and complete fixture metadata from `/v1/evaluation-gates` so it matches the shared runtime evaluation-gates schema.
- `apps/gp-visit-jp-runtime/src/main.py` now returns minimal `curriculum` and `skill_world` fields in progress snapshots so GP finish/progress responses match the shared runtime progress contract.
- `scripts/*.sh` now have executable bits so TODO-listed direct script commands work in addition to `make` and `bash` invocation.

Acceptance:

- Current Alpha is accepted as a working local multi-runtime training platform baseline.
- The MR product path is accepted for text-based scenario practice, review, progress, records, team summary, and admin read-only operations.
- The GP spike is accepted as an architecture contract proof, not as a full second product.
- Production multi-user operation is not accepted yet; it remains the next phase.

### AR2. Current Functional List

Status: [x]

Goal:
Summarize the functionality that is verified enough for local Alpha usage.

Functional list:

- MR training runtime:
  - 8 `mr_visit_jp` scenarios.
  - Scenario/persona/playbook-driven text session start, turn, finish, review, events, progress, and evaluation gates.
  - 7-subskill scoring with evidence-linked review details.
  - Skill Channel and Compliance Channel separation.
  - Compliance severity and positive compliance evidence.
  - Coach continuity, frozen teaching-plan context, learner memory, recurring weakness clusters, mastery/review status, curriculum state, skill-world state, and explainable practice path.
  - File persistence as the default local mode.
  - SQL persistence interfaces, SQL metadata, Alembic migration assets, SQL stores, and file-to-SQL import tooling.

- GP spike runtime:
  - 2 `gp_visit_jp` scenarios.
  - Minimal domain-owned subskills, compliance rules, prompt context, runtime contract endpoints, events, review, progress, curriculum, and skill-world payloads.
  - Shared runtime contract compatibility through Hermes skill-scoped routes.

- Hermes orchestrator:
  - Thin proxy/orchestrator boundary.
  - Skill registry routing for `mr_visit_jp` and `gp_visit_jp`.
  - Primary MR compatibility routes.
  - Skill-scoped runtime contract coverage.

- Web Alpha:
  - `/` dashboard.
  - `/scenarios` scenario selection.
  - `/sessions/[id]` live session.
  - `/sessions/[id]/review` and `/records/[id]/review` evidence-backed review.
  - `/records` historical records with filters and URL state.
  - `/records/[id]` replay/detail view.
  - `/progress` learner progress dashboard and practice path.
  - `/team` supervisor/team summary view.
  - `/admin` read-only prompt/evaluation gate operations view.

- Model and prompt operations:
  - Prompt profile registry.
  - Prompt builder package.
  - OpenAI-compatible provider hardening with deterministic fallback.
  - Offline fixture dataset lifecycle and fixture coverage reporting.
  - Local human review feedback export/import/candidate-preview path.

- Tooling:
  - `make bootstrap`
  - `make doctor`
  - `make validate-content`
  - `make check-no-reference-imports`
  - `make seed-mr-visit-jp`
  - `make evaluate-mr-visit-jp-fixtures`
  - `make stack-up`
  - `make smoke-check`
  - `make stack-down`

Acceptance:

- The local Alpha can demonstrate a complete text training loop from scenario selection through review and progress.
- The platform can route at least two skills without moving domain logic into Hermes.
- The roadmap can now move from local Alpha validation to production data, identity, planning, and marketplace work.

### AR3. Current Usage Guide

Status: [x]

Goal:
Record the accepted local usage path for developers, reviewers, and product stakeholders.

Developer setup:

```bash
make bootstrap
make doctor
make validate-content
make stack-up
make smoke-check
make stack-down
```

When default ports are already occupied:

```bash
WEB_PORT=3310 HERMES_PORT=8010 MR_RUNTIME_PORT=8110 GP_RUNTIME_PORT=8210 make stack-up
WEB_PORT=3310 HERMES_API_BASE=http://127.0.0.1:8010 MR_VISIT_JP_RUNTIME_BASE=http://127.0.0.1:8110 GP_VISIT_JP_RUNTIME_BASE=http://127.0.0.1:8210 make smoke-check
WEB_PORT=3310 HERMES_PORT=8010 MR_RUNTIME_PORT=8110 GP_RUNTIME_PORT=8210 make stack-down
```

Product walkthrough:

1. Open Web at `http://127.0.0.1:3000`.
2. Use `/scenarios` to start an MR session.
3. Send learner turns in `/sessions/[id]`.
4. Finish the session and inspect `/sessions/[id]/review`.
5. Use `/progress` to inspect progress, curriculum state, practice path, and next scenario.
6. Use `/records` and `/records/[id]` to inspect history and replay markers.
7. Use `/team` for supervisor-level aggregate view.
8. Use `/admin` for read-only prompt profile, rollout gate, fixture, and online metric visibility.

API smoke path:

- Web proxy: `/api/runtime/scenarios`, `/api/runtime/sessions/start`, `/api/runtime/sessions/[id]/turn`, `/api/runtime/sessions/[id]/finish`, `/api/runtime/sessions/[id]/review`, `/api/runtime/learners/[id]/progress`.
- Hermes primary MR routes: `/v1/scenarios`, `/v1/sessions/start`, `/v1/sessions/{id}/turn`, `/v1/sessions/{id}/finish`, `/v1/sessions/{id}/review`, `/v1/learners/{id}/progress`.
- Hermes skill routes: `/v1/skills`, `/v1/skills/mr_visit_jp/*`, `/v1/skills/gp_visit_jp/*`.
- Runtime health: `/healthz`.

Data modes:

- Default local data mode is file persistence under `apps/mr-visit-jp-runtime/.data/` or `MR_RUNTIME_DATA_DIR`.
- SQL mode exists behind `MR_RUNTIME_PERSISTENCE_MODE=sql` and `MR_RUNTIME_SQLALCHEMY_URL`, but it is not yet the accepted default deployment path.
- Demo seeding is explicit through `make bootstrap` and `make seed-mr-visit-jp`; runtime boot defaults to `MR_RUNTIME_DEMO_SEED_MODE=manual`.

Acceptance:

- A reviewer can run the local stack and inspect the main product path without reading raw JSON.
- A developer can run deterministic regression checks before changing runtime, Web, prompt, or domain assets.

### AR4. Accepted Gaps And Next-Phase Triggers

Status: [x]

Goal:
Separate accepted Alpha limitations from issues that must drive the next roadmap.

Accepted gaps:

- Production persistence is not accepted yet. SQL schema, stores, migrations, and import tools exist, but the accepted smoke path still uses file persistence.
- PostgreSQL is present in `docker-compose.yml`, but runtime SQL mode is not yet a first-class `make stack-up` path with migrations, seed/import, and smoke validation.
- `.env.example` documents Postgres connection pieces but does not yet expose the runtime's canonical `MR_RUNTIME_PERSISTENCE_MODE` and `MR_RUNTIME_SQLALCHEMY_URL` settings.
- `docker-compose.yml` still uses generic `POSTGRES_URL` style variables for app services instead of the runtime's canonical SQLAlchemy URL contract.
- Identity is not production-ready. Current isolation is local/header-based and test-covered, but there is no full Web login, session management, auth provider integration, or production RBAC enforcement.
- The supervisor/team view is useful but still depends on local/demo data and role context passed through request parameters/headers.
- The admin view is read-only. Admins cannot yet define training plans, assign goals, or manage learner cohorts.
- There is no Skill Marketplace. The registry can list and route registered skills, but users cannot browse, install, enable, disable, version, or train marketplace skills.
- Multi-skill dashboards are not yet productized. MR has a rich learner dashboard; GP is a contract spike with minimal display value.
- Human review feedback is local-only and intentionally not connected to production reviewer identity or permission workflow yet.

Next-phase triggers:

- Move durable data and deployment smoke to PostgreSQL before marketplace or broad multi-user workflows.
- Replace trusted local headers with real auth/session-derived organization and role context before exposing cross-learner data.
- Let admin-defined plans consume the existing curriculum/recommendation/teaching-plan model instead of creating a separate planning system.
- Treat Skill Marketplace installation as an organization-scoped capability state, not just a UI list of routes.
- Keep Hermes thin while adding platform identity, skill installation, and supervisor boundaries.

### AR5. Acceptance Recovery 2026-05-02

Status: [x]

Goal:
Recover the repository from the 2026-05-02 acceptance blockers and make P0/P1/P2 verification repeatable.

P0 scope:

- Fix Web TypeScript blockers in cross-skill dashboard UI.
- Fix Hermes marketplace tests so they load the Hermes app explicitly instead of accidentally importing the MR runtime `main.py`.
- Fix marketplace metadata tests so their manifest fixtures satisfy the shared skill manifest schema.
- Align Hermes runtime contract tests with org-scoped skill installation enforcement.
- Make `make smoke-check` work against `AUTH_MODE=mock` by logging into Web with a mock user and reusing the session cookie.

P1 scope:

- Add a non-interactive Web ESLint configuration.
- Remove `next/font/google` from the production build path so local/CI builds do not depend on `fonts.gstatic.com`.
- Upgrade Web to Next.js 15.5.15 to clear the critical Next.js audit findings reported against 15.3.0.
- Update README's next-work section so it no longer points at already-completed registry/event/evidence work.

P2 scope:

- Expand CI into an acceptance matrix for Python contracts, fixture gates, MR SQL mode, and Web lint/typecheck/build.
- Add regression coverage for mock-auth smoke login and unauthenticated OIDC smoke failure handling.
- Add a browser-level manual walkthrough checklist under `tests/e2e/WEB_WALKTHROUGH.md` until Playwright automation lands.

Verification run:

```bash
scripts/check-no-reference-imports.sh
bash -n scripts/*.sh
make validate-content
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests apps/hermes-orchestrator/tests apps/gp-visit-jp-runtime/tests tests/integration packages/prompt-builder/tests packages/evaluation-core/tests packages/skill-registry/tests
MR_RUNTIME_PERSISTENCE_MODE=sql ./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests
make evaluate-mr-visit-jp-fixtures FORMAT=json
pnpm lint
pnpm typecheck
pnpm build
make smoke-check
```

Results:

- Reference import guard passes.
- Shell syntax checks pass.
- Domain content validation passes.
- Python contract suite passes: 309 tests.
- MR SQL mode passes: 226 passed, 4 skipped.
- MR offline fixture gate passes: 45/45 fixtures.
- Web lint, typecheck, and production build pass.
- Local smoke passes through Web auth, Web runtime proxy, Hermes, MR runtime, and GP runtime.
- `npm audit --omit=dev` no longer reports the critical Next.js 15.3.0 advisory set after upgrading to Next.js 15.5.15.

Accepted remaining work:

- ESLint is now non-interactive, but several strict rules are temporarily disabled to capture the current baseline. Re-enable them incrementally.
- CI covers acceptance commands and the browser walkthrough is documented; automated Playwright e2e is still a future P2 item.
- `npm audit --omit=dev` still reports moderate PostCSS advisories through Next.js' dependency chain; npm does not currently provide a non-breaking fix for this dependency set.
- The repository still needs an initial baseline commit/tag so future reviews can be diff-based.

## 16. Suggested Next Sprints

Phase K (K0-K6) established the technical foundation for SQL persistence, identity models, training plans, and skill marketplace routing. The next phase — Phase L: Production Platform Hardening — turns these foundations into accepted production capabilities.

Planning insights:

- PostgreSQL must become the accepted default path before identity, organization sharing, or marketplace state can be durable.
- Multi-user auth with a real OIDC provider is the prerequisite for cross-learner data sharing, supervisor dashboards, and admin plan management.
- Admin training plans should build on the existing curriculum, teaching plan, and recommendation infrastructure rather than duplicating learning logic in Web.
- The Skill Marketplace should start as an org-scoped install lifecycle for trusted bundles; untrusted runtime code execution is out of scope.

### L0: PostgreSQL First-Class Mode (complete)

1. Refactor `seed_demo_data.py` to use the store factory so demo data can seed into SQL.
2. Add SQL-mode test infrastructure (`conftest.py`) with data isolation between tests.
3. Unskip API tests that were gated behind `MR_RUNTIME_PERSISTENCE_MODE != sql`.
4. Add `make dev-up-sql-stack` for the full SQL workflow from clean state.
5. Fix architectural issues (TrainingPlanStore protocol location, misleading error messages).

Exit: 230 passed (file), 224 passed + 6 skipped (SQL). `make dev-up-sql-stack` works end-to-end.

### L1: Real Identity And Organization RBAC (complete)

1. Alembic migration 0003 adds `org_id` columns to sessions, learners, learner_progress_snapshots, session_events with composite indexes.
2. SQL stores now filter by `org_id` in all methods (get, list_all, upsert, create).
3. `sql_codec.py` updated — `build_event_row()` and `build_progress_snapshot_row()` accept `org_id`.
4. `_upsert_learner` includes `org_id` in learners table INSERT/UPDATE.
5. 2 previously-skipped org isolation tests now pass in SQL mode (unskipped).
6. Generic OIDC Discovery added: `apps/web/src/lib/oidc.ts`, login/callback routes, `AUTH_MODE=oidc` support.
7. Web auth, runtime-route, auth-context, login page, site-header, scenarios, home-dashboard all handle oidc mode.
8. Cross-org data access is blocked in SQL mode (test_session_isolation_across_orgs passes).

Exit: 230 passed (file), 226 passed + 4 skipped (SQL). Cross-org isolation verified in both modes.

### L2: Admin Training Plans And Goal Assignment

1. Add Web admin UI for creating training plans with observable goals.
2. Connect assigned plans to session start, review, and progress.
3. Add supervisor view for plan completion and evidence-backed outcomes.

Exit signal:
An admin can assign a plan to a learner, and completed sessions update plan progress with evidence-backed status.

### L3: Skill Marketplace Install Lifecycle

1. Add org-scoped install/enable/disable state for registered skills.
2. Add marketplace UI listing available and installed skills.
3. Route training entry points through installed skill state.

Exit signal:
An organization can install a skill and learners can train against it without changing Hermes routing code.

## 17. Phase K: Networked Multi-User Skill Platform

Theme:
Move from accepted local Alpha to a durable, networked, multi-user platform where organizations can manage users, install skills, assign training goals, and inspect evidence-backed dashboards.

### K0. PostgreSQL Runtime Mode And Migration Smoke

Status: [x]

Goal:
Make PostgreSQL the accepted networked persistence path while preserving file mode for fast local development.

Why:
The current runtime has SQL schema, stores, Alembic assets, and import tooling, but the accepted smoke path still uses local files. Multi-user usage, organization sharing, manager dashboards, and skill marketplace state should not be built on local file persistence.

Files to read:

- `apps/mr-visit-jp-runtime/src/runtime_config.py`
- `apps/mr-visit-jp-runtime/src/persistence/store_factory.py`
- `apps/mr-visit-jp-runtime/src/persistence/sql_stores.py`
- `apps/mr-visit-jp-runtime/alembic.ini`
- `apps/mr-visit-jp-runtime/alembic/versions/*.py`
- `scripts/import-runtime-sql.sh`
- `scripts/stack-up.sh`
- `scripts/smoke-check.sh`
- `.env.example`
- `docker-compose.yml`
- `README.md`

Tasks:

- Add canonical SQL runtime settings to `.env.example`:
  - `MR_RUNTIME_PERSISTENCE_MODE=file|sql`
  - `MR_RUNTIME_SQLALCHEMY_URL=postgresql+psycopg://...`
- Align `docker-compose.yml` with the runtime's canonical SQLAlchemy URL instead of generic unused database variables.
- Add a documented SQL local path:
  - start Postgres
  - run Alembic migration
  - seed or import demo data
  - start runtime in SQL mode
  - run smoke check
- Add a `make` target or script for SQL migration readiness if the existing import script is not enough.
- Ensure `/healthz` or diagnostics clearly reports `persistence_mode=sql`.
- Run runtime API tests in both file mode and SQL mode when a database is available.
- Keep SQL behind store interfaces; do not move scoring, recommendation, or curriculum logic into SQL queries.

Acceptance:

- File mode remains the default and passes the existing smoke path.
- SQL mode can create a fresh schema, start the runtime, and pass session start, turn, finish, review, progress, events, and evaluation-gates API tests.
- A local PostgreSQL-backed stack can show training records and progress in Web after seeding or migration.
- SQL configuration is documented with one canonical environment variable set.

Verification:

```bash
docker compose up -d postgres
MR_RUNTIME_PERSISTENCE_MODE=sql MR_RUNTIME_SQLALCHEMY_URL=postgresql+psycopg://cosi:cosi@127.0.0.1:5439/cosi ./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_runtime_api.py apps/mr-visit-jp-runtime/tests/test_api_response_contracts.py
MR_RUNTIME_PERSISTENCE_MODE=sql MR_RUNTIME_SQLALCHEMY_URL=postgresql+psycopg://cosi:cosi@127.0.0.1:5439/cosi make smoke-check
```

Do not:

- Remove file mode.
- Make Web talk directly to PostgreSQL.
- Put domain scoring, compliance interpretation, or recommendation ranking into database triggers or SQL views.

### K1. Networked Data Read Models And Environment Wiring

Status: [x]

Goal:
Make training records, progress, team reports, admin metrics, and skill lists work against deployed backend services and durable stores, not only same-machine local files.

Why:
The product must be viewable by learners and supervisors across machines. Web should continue to use backend APIs, but environment wiring, read models, and deployment defaults need to assume networked services and PostgreSQL-backed state.

Files to read:

- `apps/web/src/lib/runtime-route.ts`
- `apps/web/src/lib/runtime-api.ts`
- `apps/web/src/app/api/runtime/**/route.ts`
- `apps/hermes-orchestrator/src/main.py`
- `apps/hermes-orchestrator/src/runtime_proxy.py`
- `apps/mr-visit-jp-runtime/src/services/organization_reports.py`
- `apps/mr-visit-jp-runtime/src/services/analytics_engine.py`
- `docs/deployment.md`
- `.env.example`

Tasks:

- Define dev, staging, and production API base URL rules for Web -> Hermes -> runtime.
- Remove ambiguous fallback behavior from production mode; local fallback may remain explicit.
- Ensure team reports, records, progress, and admin gates read from authoritative backend APIs only.
- Add environment validation for required production/staging base URLs.
- Add diagnostics that show which upstream Web is using without exposing secrets.
- Add documented networked smoke steps for Web/Hermes/runtime on non-default hosts.

Acceptance:

- A Web deployment can point to a remote Hermes endpoint and complete the accepted smoke path.
- Production mode fails fast when required API base URLs are missing.
- Records, progress, team, and admin pages do not depend on local filesystem access from Web.

Verification:

```bash
pnpm typecheck
pnpm build
make smoke-check
```

Do not:

- Add database access to Next route handlers.
- Let production silently fall back from Hermes to a local runtime.

### K2. Multi-User Login And Organization RBAC

Status: [x]

Goal:
Add real users, login sessions, organizations, roles, and membership enforcement while preserving auth-disabled local demo mode.

Why:
The current Alpha has learner ids and org isolation tests, but production multi-user usage cannot trust browser-supplied learner/org headers. User identity must become the source of learner ownership, supervisor scope, and admin permissions.

Files to read:

- `apps/web/src/app/layout.tsx`
- `apps/web/src/components/site-header.tsx`
- `apps/web/src/lib/runtime-api.ts`
- `apps/hermes-orchestrator/src/main.py`
- `apps/mr-visit-jp-runtime/src/main.py`
- `apps/mr-visit-jp-runtime/tests/test_multi_tenancy.py`
- `packages/shared-schemas/schemas/runtime_organization_reports_response.schema.json`
- `docs/architecture/data-flow.md`

Tasks:

- Choose and document the first auth mode:
  - local dev mock auth
  - production-ready provider adapter or signed session token boundary
- Define models for user, learner, organization, role, membership, and permission grants.
- Define roles at minimum:
  - learner
  - supervisor
  - organization_admin
  - content_admin
  - platform_admin
- Ensure Web derives learner/org/role context from the authenticated session, not editable query params.
- Ensure Hermes forwards trusted identity context to runtimes.
- Ensure runtime rejects unauthorized cross-learner and cross-organization access in auth-enabled mode.
- Preserve `AUTH_MODE=disabled` or equivalent for local demo learners.
- Add audit metadata to sensitive access paths: review read, transcript read, admin action, plan assignment.

Acceptance:

- Auth-disabled local mode still supports demo learners.
- Auth-enabled mode requires login.
- Learners can access only their own sessions/progress unless a sharing rule grants access.
- Supervisors can access organization aggregate reports and permitted learner drill-down.
- Admin routes require admin roles.
- Cross-org and cross-role negative tests pass.

Verification:

```bash
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_multi_tenancy.py
./.venv/bin/python -m pytest apps/hermes-orchestrator/tests
pnpm typecheck
pnpm build
make smoke-check
```

Do not:

- Trust raw `X-Org-ID`, `learner_id`, or `viewerRole` from browsers in production mode.
- Expose raw transcripts to supervisors before role and sharing policy allow it.
- Break local demo mode.

### K3. Learner Data Sharing And Supervisor Access Policy

Status: [x]

Goal:
Define and implement controlled sharing of learner training data across learners, supervisors, admins, and organizations.

Why:
Training data includes transcripts, compliance findings, coach feedback, progress, and potentially sensitive performance signals. Sharing must be explicit before team dashboards, manager review, or marketplace reporting expands.

Files to read:

- `apps/mr-visit-jp-runtime/src/services/organization_reports.py`
- `apps/mr-visit-jp-runtime/src/persistence/interfaces.py`
- `apps/web/src/features/supervisor/team-flow.tsx`
- `apps/web/src/features/sessions/records-flow.tsx`
- `apps/web/src/features/sessions/review-flow.tsx`
- `packages/shared-schemas/schemas/runtime_organization_reports_response.schema.json`
- `docs/architecture/data-flow.md`

Tasks:

- Define access levels for each artifact:
  - aggregate metrics
  - session metadata
  - scores and diagnosis
  - compliance flags
  - coach feedback
  - transcript text
  - human review corrections
- Add policy checks to runtime or platform boundary before returning learner-specific artifacts.
- Add supervisor-safe redaction or summary views when transcript access is not granted.
- Add sharing grants for learner-to-supervisor, cohort-to-supervisor, and organization-admin cases.
- Add audit log entries for transcript and review detail access.
- Add UI states explaining when a detail view is restricted.

Acceptance:

- Team summary can be viewed without exposing unauthorized transcript text.
- Supervisor drill-down respects artifact-level permissions.
- Audit records identify who accessed sensitive learner artifacts and why.
- Negative tests prove unauthorized transcript/review reads fail.

Verification:

```bash
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_multi_tenancy.py
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_runtime_api.py
pnpm build
```

Do not:

- Use UI hiding as the only permission control.
- Treat all supervisor access as full transcript access.

### K4. Admin Training Plans And Goal Assignment

Status: [x]

Goal:
Let admins or supervisors define training plans, assign goals to learners/cohorts, and track completion with evidence-backed outcomes.

Why:
The current system can recommend practice paths, but managers need to set intentional training plans and target outcomes. This should reuse curriculum, teaching plan, progress, and recommendation logic instead of creating an unrelated planning layer.

Files to read:

- `domains/mr_visit_jp/curriculum/core.yaml`
- `apps/mr-visit-jp-runtime/src/services/curriculum_service.py`
- `apps/mr-visit-jp-runtime/src/services/recommendation_engine.py`
- `apps/mr-visit-jp-runtime/src/services/coach_continuity.py`
- `apps/mr-visit-jp-runtime/src/services/progress_tracker.py`
- `apps/web/src/features/admin/admin-flow.tsx`
- `apps/web/src/features/supervisor/team-flow.tsx`
- `apps/web/src/features/sessions/progress-flow.tsx`

Tasks:

- Define a training plan model:
  - plan id
  - skill id
  - organization id
  - owner user id
  - assigned learner/cohort ids
  - target subskills
  - required scenarios or curriculum stages
  - due date or target window
  - observable goal criteria
  - success threshold
  - review cadence
  - status
- Add runtime/platform APIs for create, update, assign, list, archive, and inspect plan progress.
- Freeze active plan context at session start when a session is launched from an assigned plan.
- Compare review results to assigned goals using transcript evidence and compliance signals.
- Feed plan status into recommendation ranking without overriding safety/compliance priority.
- Add admin UI for plan creation and assignment.
- Add supervisor UI for cohort completion, at-risk learners, and evidence-backed goal outcomes.

Acceptance:

- An admin can create a plan for a target skill and assign it to a learner or cohort.
- A learner can start a session from an assigned plan.
- Review shows whether the assigned target behavior was achieved, partially achieved, not achieved, or not observable.
- Progress and team views show plan completion status and evidence-backed blockers.
- Recommendation policy can prioritize assigned goals while still respecting compliance risk.

Verification:

```bash
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_continuity.py apps/mr-visit-jp-runtime/tests/test_progress_tracker.py apps/mr-visit-jp-runtime/tests/test_recommendation_fixtures.py
pnpm typecheck
pnpm build
make smoke-check
```

Do not:

- Store vague goals such as "improve communication" without observable success criteria.
- Let Web compute authoritative plan completion.
- Let assigned goals suppress high-severity compliance remediation.

### K5. Skill Marketplace Registry And Install Lifecycle

Status: [x]

Goal:
Create the first controlled Skill Marketplace loop where organizations can discover, enable, disable, and train trusted skill bundles.

Why:
COSI should become a Skill World platform, but marketplace capability must be grounded in existing registry/runtime contracts. The first marketplace should manage trusted internal or curated skill bundles, not arbitrary untrusted code execution.

Files to read:

- `packages/skill-registry/README.md`
- `domains/mr_visit_jp/manifests/skill.yaml`
- `domains/gp_visit_jp/manifests/skill.yaml`
- `apps/hermes-orchestrator/src/main.py`
- `apps/hermes-orchestrator/src/runtime_proxy.py`
- `apps/web/src/lib/runtime-api.ts`
- `apps/web/src/app/scenarios/page.tsx`
- `docs/architecture/skill-registry-contract.md`
- `packages/shared-schemas/schemas/skill_manifest.schema.json`

Tasks:

- Extend skill manifest metadata for marketplace display:
  - title
  - summary
  - provider
  - supported locales
  - modality
  - maturity
  - required runtime actions
  - optional runtime actions
  - version
  - compatibility
  - privacy/data notes
- Add organization skill installation state:
  - available
  - installed
  - disabled
  - upgrade_available
  - blocked
- Add APIs for listing available skills, listing installed skills, installing, disabling, and checking compatibility.
- Add Web marketplace UI with installed/available skill filters.
- Route training entry points through installed skill state.
- Add tests proving uninstalled skills cannot be started by learners in an organization unless local demo mode allows it.

Acceptance:

- Web can show a marketplace list of trusted skills.
- An organization admin can install or disable a skill.
- Learners can train only installed/enabled skills in auth-enabled mode.
- Hermes still routes through registry metadata and remains thin.
- MR remains the primary mature skill; GP remains marked as a spike unless deepened.

Verification:

```bash
./.venv/bin/python -m pytest apps/hermes-orchestrator/tests apps/gp-visit-jp-runtime/tests apps/mr-visit-jp-runtime/tests/test_api_response_contracts.py
pnpm build
make smoke-check
```

Do not:

- Execute arbitrary uploaded runtime code in-process.
- Move MR scoring or compliance logic into marketplace code.
- Treat a skill as installed globally when installation should be organization-scoped.

### K6. Installed Skill Training Dashboard

Status: [x]

Goal:
Provide learner and supervisor dashboards that work across installed skills while preserving skill-specific review semantics.

Why:
Once users can install skills, they need a dashboard for training status, recent sessions, goals, and next actions across skills. The dashboard should summarize cross-skill progress without flattening domain-specific scoring rules into a misleading universal score.

Files to read:

- `apps/web/src/features/home/home-dashboard.tsx`
- `apps/web/src/features/sessions/progress-flow.tsx`
- `apps/web/src/features/sessions/records-flow.tsx`
- `apps/web/src/features/supervisor/team-flow.tsx`
- `apps/mr-visit-jp-runtime/src/services/progress_tracker.py`
- `apps/mr-visit-jp-runtime/src/services/organization_reports.py`
- `apps/gp-visit-jp-runtime/src/main.py`
- `packages/shared-schemas/schemas/runtime_progress_snapshot_response.schema.json`
- `packages/shared-schemas/schemas/runtime_organization_reports_response.schema.json`

Tasks:

- Define cross-skill dashboard summary fields:
  - installed skill count
  - active skill count
  - sessions by skill
  - goals by skill
  - next recommended action by skill
  - compliance or policy attention count by skill
  - recent history by skill
- Keep skill-specific score labels and review components where needed.
- Add skill filters to records, progress, team, and admin pages.
- Add supervisor dashboard grouping by organization, skill, cohort, learner, and goal status.
- Add empty states for installed skills with no sessions.
- Add compatibility behavior for spike skills with minimal progress payloads.

Acceptance:

- A learner can see all installed skills and continue the next recommended practice for each.
- A supervisor can see which skills and learners need attention without reading raw transcripts first.
- Skill-specific review semantics remain intact; cross-skill UI does not pretend all skills share the same rubric.
- GP spike appears as a limited-capability skill rather than a full MR-equivalent product.

Verification:

```bash
pnpm typecheck
pnpm build
make smoke-check
```

Do not:

- Collapse all skill progress into one opaque universal score.
- Require every future skill to implement MR-specific subskills or compliance concepts.

## 18. Phase-Level Exit Contracts

This section defines how each major phase is judged complete. A phase is not complete just because its tickets are merged; it is complete only when the phase-level target, test method, expected result, and acceptance standard are all satisfied.

### Immediate Execution Queue

Target:
Turn the current Alpha into a safe local collaboration baseline. A fresh engineer should be able to bootstrap, run the Web + Hermes + runtime stack, execute one MR training loop, and understand the next architecture spine without accidentally coupling to `references/`.

Test method:
Run the reference-import guard, shell syntax checks, focused runtime/Hermes tests, Web build/typecheck when UI contracts change, and the full local stack smoke path from `make stack-up` to `make smoke-check` to `make stack-down`.

Expected test result:
No runtime path imports from `references/`; stack scripts start and stop all three services; smoke check completes `scenarios -> start -> turn -> finish -> review -> progress`; demo seeding behavior is explicit; event/review changes remain backward-compatible.

Acceptance standard:
The next AI engineer can start from a fresh clone, follow README commands, reach a working local app, and execute Q/R tasks without asking for missing setup, hidden seed behavior, or reference-code policy clarification.

### Phase R: Reference-Inspired Architecture Foundation

Target:
Convert the useful Hermes-agent and DeepTutor patterns into COSI-native architecture: registry routing, unified domain context, event envelope, doctor diagnostics, persistence/search blueprint, prompt asset management, and trace-safe logging.

Test method:
Review `docs/architecture/reference-mapping.md`, ADRs, registry/context/event specs, and implementation tests. Run import guards, registry unit tests, context propagation tests, event schema tests, doctor script checks, prompt snapshot tests, and smoke checks after each runtime-facing change.

Expected test result:
Registry concepts are unambiguous; Hermes remains thin; domain context carries learner/session/scenario/prompt/trace data; events share a stable envelope; doctor output identifies setup failures; prompt rendering is deterministic; no copied reference subsystem enters runtime paths.

Acceptance standard:
Future domain work can be implemented through registry, context, and event contracts without hard-coding MR-only assumptions into Hermes, Web, or shared packages.

### Phase A: Alpha Hardening

Target:
Make the existing single-domain Alpha reliable, inspectable, and safe to iterate before broadening scope.

Test method:
Run runtime API tests, Hermes proxy/contract tests, file-store corruption and idempotency tests, stack smoke checks, shell checks, and transcript/recommendation regression fixtures.

Expected test result:
API payloads remain compatible across runtime, Hermes, and Web; invalid local JSON does not crash unrelated sessions; retrying finish/progress is idempotent; smoke failures identify the failing service and URL; regression fixtures catch scoring/recommendation drift.

Acceptance standard:
The MR Alpha can be demoed repeatedly with predictable behavior, diagnosable failures, and enough regression coverage that small changes do not silently break the core training loop.

### Phase B: Training Quality

Target:
Improve the pedagogical value of MR training through measurable training-quality metrics, scenario playbooks, compliance-first signals, continuity-based teaching plans, and explainable practice paths.

Test method:
Run state-machine heuristic tests, scenario asset validation, compliance fixture tests, transcript evaluation fixtures, recommendation ranking fixtures, and multi-session learner memory/progress tests.

Expected test result:
Busy-doctor, evidence-check, adverse-event, objection, and weak-close scenarios produce distinct deterministic guidance; compliance severity affects recommendations without replacing skill scoring; continuity plans are frozen at session start and checked in review; practice paths are ranked and explainable. Training-quality fixtures check not only schema validity but also evidence specificity, diagnosis clarity, coaching actionability, compliance usefulness, and recommendation explainability.

Acceptance standard:
The system behaves like structured MR training rather than a generic chat loop, and every important coaching/recommendation decision can be explained from scenario assets, transcript evidence, compliance rules, learner history, or teaching-plan outcomes. The system can explain every important coaching or recommendation decision from scenario playbooks, transcript evidence, compliance rules, learner history, or teaching-plan outcomes.

### Phase C: Product UX And Learning Experience

Target:
Make the Web app usable as a repeated training product, starting with minimal evidence-backed review clarity and then expanding into live-session polish, progress dashboard, records filtering, and replay.

Test method:
Run `pnpm build`, `pnpm typecheck`, runtime smoke checks, API compatibility tests, manual browser walkthroughs for active session/review/progress/records, and automated UI/e2e tests once the project adds them.

Expected test result:
Live sessions handle loading/submitting/finish/error states; refresh does not lose active session context; review renders evidence-linked feedback and old payload fallbacks; progress differs meaningfully across demo learners; records filters preserve URL state and replay event markers.

Acceptance standard:
A learner can choose a scenario, complete practice, understand review evidence, see progress, and start the next recommended practice without inspecting raw JSON or relying on developer knowledge.

### Phase D: Production Persistence Backbone

Target:
Move from local file persistence to SQL-backed storage only after persistence behavior semantics and store interfaces are explicit, without changing public runtime/Hermes/Web behavior.

Test method:
Run store interface tests against file and SQL implementations, Alembic migration tests on a fresh database, file-to-SQL dry-run/apply tests, API tests in both `file` and `sql` store modes, and smoke checks for each mode when feasible.

Expected test result:
File mode remains default and stable; SQL mode preserves sessions, turns, events, reviews, progress snapshots, recommendations, prompt context, and learner ids; migrations create the expected schema; migration reports invalid artifacts without corrupting valid data.

Acceptance standard:
The platform can switch persistence implementations behind configuration while keeping domain logic, API payloads, review behavior, and Web flows unchanged.

### Phase E: Platformization And Multi-Domain Readiness

Target:
Prove that COSI can route and run more than one domain through a shared platform contract while keeping domain logic isolated.

Test method:
Run skill-registry unit tests, manifest validation tests, Hermes multi-skill routing tests, reusable runtime contract tests, MR regression tests, and a tiny second-domain spike smoke path.

Expected test result:
Hermes lists registered skills and routes actions through registry metadata; unknown skills/actions fail clearly; `mr_visit_jp` remains unchanged; the second domain satisfies the minimum runtime contract without copying MR internals.

Acceptance standard:
A future domain team can implement a small domain by following the manifest and runtime contract, not by reading or modifying MR runtime internals. Shared package expansion is accepted only when the second-domain spike proves the abstraction is not MR-specific.

### Phase F: Accounts, Organizations, And Operations

Target:
Move from local single-user Alpha toward real learner/team operation with identity, learner ownership, supervisor views, and admin visibility.

Test method:
Run auth-disabled local tests, auth-enabled integration tests, RBAC negative tests, cross-learner access tests, supervisor aggregate fixture tests, and admin read-only workflow tests.

Expected test result:
Local demo mode still works without auth; auth-enabled mode prevents cross-learner data access; supervisors can see aggregate progress without unauthorized transcript exposure; operators can inspect prompt profile, gate status, asset validation, and fixture results.

Acceptance standard:
The system can support organization-scoped learners and supervisors without weakening local development, privacy boundaries, or domain runtime ownership.

### Phase G: Curriculum, Practice Paths, And Skill World

Target:
Turn repeated scenarios into an intentional learning journey with curricula, mastery status, revisit logic, and a world layer grounded in real progress.

Test method:
Run curriculum asset validation, recommendation practice-path fixtures, mastery threshold tests, spaced-revisit tests, progress dashboard tests, and regression checks proving world state derives from training evidence.

Expected test result:
Learners have curriculum stages with prerequisites and completion criteria; recommendations respect both weakness and curriculum stage; mastery states change only from rolling evidence; world/achievement UI reflects real sessions and skill progress.

Acceptance standard:
The product can explain where a learner is, why that stage matters, what to practice next, and when a skill is improving or mastered.

### Phase H: Model Ops And Prompt System

Target:
Make model-assisted behavior safe, measurable, replaceable, and testable through prompt builder, provider hardening, and evaluation dataset lifecycle.

Test method:
Run prompt snapshot tests, malformed provider response tests, timeout/retry tests, structured output schema tests, offline evaluation gates, fixture coverage reports, and prompt profile promotion/blocking checks.

Expected test result:
Prompt rendering is deterministic and versioned; model failures do not block session finalization; review metadata records whether model, mock, or fallback produced artifacts; fixture gates summarize deltas and block unsafe prompt profiles.

Acceptance standard:
Model behavior can be changed experimentally without losing schema safety, regression visibility, or the ability to fall back to deterministic training behavior.

### Phase I: Voice And Multimodal Training

Target:
Extend the training loop to voice and multimodal inputs only after text scoring, events, persistence, and review evidence are stable.

Test method:
Run all text-session regression tests, mocked STT/TTS integration tests, audio artifact schema tests, voice session smoke tests, latency/interruption scenario tests, and review compatibility tests.

Expected test result:
Text-only paths remain unchanged; voice sessions produce transcript-aligned turns and artifact references; voice-specific metrics are stored separately unless explicitly mapped to a scoring signal; interruptions and retries do not corrupt session state.

Acceptance standard:
One voice-enabled scenario can run end to end without changing the semantics of existing text scoring, review evidence, or progress tracking.

### Phase J: Release, Deployment, And Reliability

Target:
Make the full system deployable, observable, and recoverable beyond a local workstation.

Test method:
Run Docker compose from a clean checkout, CI Python/Web/shell/schema jobs, health/readiness checks, environment config validation, smoke checks in containerized mode, and backup/restore dry runs for SQL mode.

Expected test result:
Web, Hermes, runtime, Postgres, and Redis start consistently; CI catches contract, build, and test failures; staging config is explicit; readiness/liveness endpoints reflect real service state; backup/restore produces usable SQL data.

Acceptance standard:
A new engineer can deploy staging from documented commands and environment variables, and the team can detect, diagnose, and recover from common service or data failures.

### Phase K: Networked Multi-User Skill Platform

Target:
Move the accepted local Alpha into a durable, networked, multi-user platform where PostgreSQL, identity, role policy, training plans, skill installation, and cross-skill dashboards are first-class product capabilities.

Test method:
Run SQL-mode runtime API tests against PostgreSQL, migration tests, file-to-SQL import tests, Web/Hermes/runtime smoke checks in SQL mode, auth-enabled RBAC negative tests, plan assignment/progress tests, marketplace install/disable tests, and cross-skill dashboard build/typecheck/smoke checks.

Expected test result:
PostgreSQL mode can run the accepted training loop end to end; auth-enabled mode derives organization and role context from login sessions; learners cannot access unauthorized data; supervisors see permitted aggregate and drill-down views; admins can assign observable goals; organizations can install trusted skills; dashboards summarize installed-skill activity without flattening domain-specific rubrics.

Acceptance standard:
The system can support real organizations with multiple users, durable shared training data, manager-assigned goals, controlled skill installation, and supervisor dashboards while keeping Hermes thin and domain logic inside domain runtimes.

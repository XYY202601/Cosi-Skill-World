# 给 AI 工程师的 TODO.md 修改指令

## 任务名称

更新 `TODO.md`：把当前路线图从“工程架构完成度优先”调整为“训练质量 + 证据化学习闭环 + 平台化边界”共同驱动。

## 任务目标

请基于现有 `COSI Skill World Master TODO`，对 TODO.md 做一次结构化修订。此次修订不是实现代码，而是更新路线图本身，让后续 AI 工程师可以更准确地执行下一阶段工作。

本次修改要达到以下目标：

1. 修正已经过时的 Suggested Next Sprint。
2. 新增训练质量定义，避免只做工程闭环、不验证教学价值。
3. 把 Scenario Playbook 从普通配置升级为教学资产。
4. 把 Review UX 提前，让 evidence-linked review 产生真实产品价值。
5. 在 SQL 持久化前新增 persistence behavior contract，避免数据库结构反向绑死业务语义。
6. 明确 Director / Doctor / Judge / Coach 四个训练角色的职责边界。
7. 把 Compliance 设计成独立一等信号，而不是评分附属品。
8. 强化 Recommendation 的可解释性，把“推荐下一个场景”升级为“练习路径”。
9. 在第二领域 Spike 前抑制过早抽象 shared packages。
10. 增加未来 Human / SME Review Feedback Loop 的路线图入口。

---

# 一、修改范围

## 允许修改

请修改 `TODO.md` 中以下部分：

- `## 0. Project Understanding`
- `## 5. Phase B: Training Quality`
- `## 6. Phase C: Product UX And Learning Experience`
- `## 7. Phase D: Production Persistence Backbone`
- `## 8. Phase E: Platformization And Multi-Domain Readiness`
- `## 11. Phase H: Model Ops And Prompt System`
- `## 15. Suggested Next Sprint`
- `## 16. Phase-Level Exit Contracts`

如果 TODO.md 中存在目录或章节编号引用，请同步更新。

## 不要修改

本次任务不要修改代码、测试、schema、domain asset 或 README。只修改 TODO.md。

不要改变已经完成项的状态，除非 TODO.md 中明显存在自相矛盾。例如：某项状态为 `[x]`，但 Suggested Next Sprint 仍把它列为下一步，应修改 Suggested Next Sprint，而不是把已完成项改回 `[ ]`。

不要删除原有架构护栏。Hermes thin、domain runtime ownership、domain assets under `domains/`、structured output validation、shared packages clean boundaries 等原则必须保留。

---

# 二、修改前必须阅读

请先阅读以下文件，确认当前 TODO.md 的上下文：

- `TODO.md`
- `docs/architecture/reference-mapping.md`
- `docs/architecture/session-store-search-blueprint.md`
- `docs/architecture/data-flow.md`
- `docs/api/hermes-orchestrator-api.md`，如果存在
- `docs/api/mr-visit-jp-runtime-api.md`，如果存在
- `domains/mr_visit_jp/manifests/skill.yaml`
- `domains/mr_visit_jp/scenarios/*.yaml`
- `domains/mr_visit_jp/rubrics/skill_model.yaml`
- `domains/mr_visit_jp/compliance/rules.yaml`

如果某些文件不存在，不要创建它们。本任务只更新 TODO.md。可以在 TODO.md 中保留相关未来任务。

---

# 三、总体编辑原则

## 原则 1：不要把 TODO.md 写成愿望清单

每个新增任务都必须包含：

- Status
- Goal
- Why
- Files to read 或 Files
- Tasks
- Acceptance
- Verification，如适用
- Do not，如适用

风格要和现有 TODO.md 保持一致。

## 原则 2：新增内容必须可执行

不要写类似“优化训练体验”“提升智能化”“完善架构”这种泛泛描述。必须写成 AI 工程师可以执行和验证的 ticket。

示例：

不推荐：

> Improve review quality.

推荐：

> Add evidence-backed review quality metrics. Each priority subskill must have a transcript evidence item, a diagnosis reason, and one next behavior suggestion. Fixture tests must assert all three fields exist for representative transcripts.

## 原则 3：先教学价值，再生产基础设施

当前系统已经有较好的工程基础。接下来 TODO.md 应强调：

- evidence-backed diagnosis
- playbook-driven training
- compliance-aware coaching
- continuity teaching plan
- explainable practice path
- learner-visible review UX

SQL、Docker、CI、Deployment 仍然重要，但不要让它们在短期路线中压过训练质量。

## 原则 4：平台化必须来自第二领域验证，而不是第一领域想象

不要把 MR 的概念过早提升到 shared packages。TODO.md 应明确：

- 第二领域 Spike 之前，不要厚化 shared packages。
- 第二领域 Spike 的目的不是做产品，而是验证 runtime contract、skill registry、prompt/rubric/event 抽象是否足够。
- shared packages 的扩展必须由至少两个领域的共同需求驱动。

---

# 四、具体修改指令

## 修改 1：在 Project Understanding 中新增“三层系统”说明

位置：

在 `### North Star` 之后，或 `### Architecture Guardrails` 之前新增一节。

新增标题：

```markdown
### Three-Layer Product Architecture
```

新增内容应表达以下意思：

COSI Skill World 应被理解为三层系统：

1. Training Runtime Layer
2. Diagnosis & Learning Layer
3. Platform & Operations Layer

请写成 TODO.md 风格的英文内容，不要用中文。

建议内容结构如下：

```markdown
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
```

注意：

- 不要移除原有 North Star。
- 不要改变 Hermes thin 的架构护栏。
- 新增内容应帮助后续工程师理解为什么 Phase B/C 要前置。

验收：

- TODO.md 中出现 Three-Layer Product Architecture。
- 三层定义清楚。
- 明确指出近期路线应优先加强 Diagnosis & Learning Layer。

---

## 修改 2：新增角色职责边界表

位置：

建议放在 `### Architecture Guardrails` 之后，或 Phase B 之前。

新增标题：

```markdown
### Training Role Ownership Boundaries
```

新增目的：

明确 Director、Doctor、Judge、Coach 的职责，避免后续 AI 工程师把评分、反馈、角色扮演和推荐混在一起。

建议新增表格：

```markdown
### Training Role Ownership Boundaries

The MR training loop uses several role-like components. Their responsibilities must stay separate:

| Component | Owns | Must not own | Inputs | Outputs |
| --- | --- | --- | --- | --- |
| Doctor | Persona-grounded doctor response and pushback | Final scoring, progress updates, recommendations | Scenario, persona, learner turn, playbook, session context | Doctor reply, pushback signal, local conversation pressure |
| Director | Turn-level training guidance and session flow signals | Final score, learner progress mutation, long-term recommendation policy | Transcript, playbook, continuity brief, event history | Next-turn guidance, recovery hint, event signals |
| Judge | Evidence-linked scoring, diagnosis, compliance detection | Motivational coaching tone, future practice planning | Transcript, rubric, compliance rules, playbook, structured events | Subskill scores, diagnosis, evidence references, compliance flags |
| Coach | Teaching feedback, behavior advice, continuity plan | Rewriting historical scores, simulating the doctor, owning raw compliance policy | Judge output, learner history, progress, recommendation context | Feedback, target behavior, teaching plan, next actions |
```

补充规则：

```markdown
Rules:

- Judge output must remain evidence-backed and schema-validated.
- Coach may explain and teach from Judge output, but must not silently change Judge scores.
- Director may guide the next turn, but must not become a heavy autonomous agent.
- Doctor behavior must remain scenario/persona/playbook-grounded.
- Recommendation policy should consume Judge, Coach, compliance, and progress signals without moving those responsibilities into Web or Hermes.
```

验收：

- 表格职责清楚。
- 明确 Judge 和 Coach 不应混合。
- 明确 Doctor 不评分，Director 不拥有最终评分和长期推荐。

---

## 修改 3：在 Phase B 前新增 B0 Training Quality Metrics Definition

位置：

在 `## 5. Phase B: Training Quality` 下，现有 B1 之前。

新增标题：

```markdown
### B0. Training Quality Metrics Definition
```

状态：

```markdown
Status: [ ]
```

新增完整 ticket。建议内容如下：

```markdown
### B0. Training Quality Metrics Definition

Status: [ ]

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
```

注意：

- 这个 ticket 是路线图任务，不要求本次实现测试。
- 如果 TODO.md 更偏向只列实现任务，也可以把 “Document how these metrics…” 写成产物。

验收：

- B0 被插入到 B1 前面。
- B0 明确说明为什么需要训练质量指标。
- B0 明确区分 deterministic fixtures 和未来 human/SME review。

---

## 修改 4：增强 B1 Scenario-Specific Playbooks

位置：

修改现有：

```markdown
### B1. Scenario-Specific Playbooks
```

目标：

把 B1 从“添加一些 optional playbook fields”升级为“把每个 scenario 的教学脚本资产化”。

请保留原来的核心意思，但做以下增强。

### 4.1 修改 Goal

将 Goal 调整为：

```markdown
Goal:
Turn each scenario into a structured teaching asset that can guide the Doctor, Director, Judge, Coach, Review, and Recommendation policy consistently.
```

### 4.2 修改 Why

如果原 B1 没有 Why，请新增：

```markdown
Why:
Current scenario data can support roleplay and scoring, but richer training behavior requires explicit teaching intent. Playbooks should make the expected visit flow, common learner failures, recovery moves, and completion signals visible as domain assets rather than hidden Python heuristics.
```

### 4.3 扩展 Tasks

把现有 Tasks 替换或扩展为：

```markdown
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
```

### 4.4 增强 Acceptance

修改为：

```markdown
Acceptance:

- All 8 scenarios include minimal but meaningful playbook data.
- Invalid playbook data fails boot with a clear asset error.
- Director/Doctor tests prove at least three scenario-specific playbook fields affect deterministic behavior.
- Playbook assets can explain the intended learning objective, expected learner behavior, common failure patterns, and recovery moves without reading Python code.
```

### 4.5 增强 Do not

保留原有 Do not，并追加：

```markdown
- Do not create generic platform playbook abstractions until a second domain proves which fields are shared.
- Do not hide scenario teaching intent inside state-machine heuristics.
- Do not require model calls to interpret playbooks in default mock mode.
```

验收：

- B1 明显从配置字段扩展为教学资产设计。
- 包含 playbook schema 和 asset quality gate。
- 明确禁止过早平台化 playbook。

---

## 修改 5：增强 B2 Compliance As First-Class Training Signal

位置：

修改现有：

```markdown
### B2. Compliance As First-Class Training Signal
```

目标：

把 Compliance 明确设计为“双通道”：Skill Channel 和 Compliance Channel。

### 5.1 修改 Goal

建议改为：

```markdown
Goal:
Make compliance a first-class training signal that runs alongside skill scoring, affects coaching and recommendation priority, and remains clearly visible without replacing subskill evaluation.
```

### 5.2 新增 Why

```markdown
Why:
In MR training, a learner can communicate well while still creating compliance risk, or handle a compliance-sensitive situation correctly even if other skills are weak. Skill feedback and compliance feedback must be separated but coordinated.
```

### 5.3 扩展 Tasks

增加以下内容：

```markdown
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
```

### 5.4 增强 Acceptance

```markdown
Acceptance:

- Compliance regression fixtures prove severe flags affect recommendation priority.
- Review page separates skill feedback from compliance signal.
- Correct compliance handling can appear as positive evidence.
- Recommendation explanations identify whether compliance, skill weakness, or both drove the next practice path.
```

### 5.5 添加 Do not

```markdown
Do not:

- Collapse compliance severity into the overall score without explanation.
- Hide compliance findings inside generic coaching text.
- Let Web define compliance interpretation logic.
- Treat compliance only as a punishment signal; correct handling should also be recognized.
```

验收：

- B2 明确 Skill Channel 和 Compliance Channel。
- 严重合规风险对 recommendation priority 有规则。
- 合规正确处理也被视为 evidence。

---

## 修改 6：增强 B3 Coaching Continuity As A Teaching Plan

位置：

修改现有：

```markdown
### B3. Coaching Continuity As A Teaching Plan
```

目标：

让 Teaching Plan 更明确地成为 session start 时冻结的学习契约，并在 Review 中对照检查。

### 6.1 扩展 Tasks

在原有任务基础上添加：

```markdown
- Store a teaching plan version or snapshot id on session start.
- Freeze the plan at session start so later progress changes do not rewrite the session's target.
- Include source evidence from previous sessions when available.
- Define success criterion in observable behavior terms, not vague improvement language.
- Compare the finalized review against the frozen plan:
  - achieved
  - partially achieved
  - not achieved
  - not observable
- Feed the result back into learner memory and recommendation policy.
```

### 6.2 增强 Acceptance

```markdown
Acceptance:

- Starting a recommended scenario includes a continuity brief tied to prior learner history.
- The teaching plan is frozen at session start and visible in session/review metadata.
- Review explains whether the target behavior improved using transcript evidence.
- Tests cover memory carry-over after at least two finalized sessions.
- Recommendation policy can use teaching-plan outcome when ranking the next practice path.
```

### 6.3 添加 Do not

```markdown
Do not:

- Let the active teaching plan mutate after a session has started.
- Store vague goals such as “improve communication” without observable success criteria.
- Display memory without turning it into a next-session behavior target.
```

验收：

- B3 明确 teaching plan snapshot / freeze 语义。
- Review 需要对照 teaching plan。
- Recommendation 可以消费 teaching-plan outcome。

---

## 修改 7：增强 B4 Recommendation Policy V2

位置：

修改现有：

```markdown
### B4. Recommendation Policy V2
```

目标：

把推荐从“下一个场景”升级为“可解释的练习路径”。

### 7.1 修改 Goal

```markdown
Goal:
Turn recommendation from a single next scenario into a short, explainable practice path that connects learner history, transcript evidence, target subskills, compliance priority, and stop conditions.
```

### 7.2 扩展 Tasks

```markdown
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
```

### 7.3 增强 Acceptance

```markdown
Acceptance:

- Progress page can show a 2-3 step practice path.
- Recommendation fixture tests cover ranking, explanation, repetition avoidance, compliance priority, and stop conditions.
- Each recommendation can answer:
  - why this scenario
  - why now
  - what to practice
  - what evidence triggered it
  - when to stop repeating it
```

### 7.4 添加 Do not

```markdown
Do not:

- Return opaque recommendations that cannot be explained from learner history, review evidence, compliance rules, or curriculum state.
- Recommend the same scenario indefinitely after improvement.
- Move recommendation ranking rules into Web.
```

验收：

- B4 明确 2-3 步 practice path。
- 每个推荐都有 why/what/evidence/stop condition。
- 加强避免重复推荐。

---

## 修改 8：拆分 C2 Review UX 为 C2a 和 C2b

位置：

修改 `## 6. Phase C: Product UX And Learning Experience` 中的 C2。

目标：

让最小 Review UX 更早交付，不被高级 replay 功能拖慢。

### 8.1 将原 C2 改名为 C2a

原：

```markdown
### C2. Review UX With Transcript Evidence
```

改为：

```markdown
### C2a. Minimal Evidence Review UX
```

### 8.2 修改 C2a 内容

```markdown
### C2a. Minimal Evidence Review UX

Status: [ ]

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
```

### 8.3 新增 C2b Advanced Transcript Linking And Replay

在 C2a 后新增：

```markdown
### C2b. Advanced Transcript Linking And Replay

Status: [ ]

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
```

验收：

- C2 被拆为 C2a/C2b。
- C2a 更早交付基本价值。
- C2b 专注高级 linking/replay。

---

## 修改 9：在 Phase D 前新增 D0 Persistence Behavior Contract

位置：

在 `## 7. Phase D: Production Persistence Backbone` 下，D1 之前。

新增标题：

```markdown
### D0. Persistence Behavior Contract
```

新增完整 ticket：

```markdown
### D0. Persistence Behavior Contract

Status: [ ]

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
```

验收：

- D0 位于 D1 之前。
- D0 明确 SQL 前先定义行为语义。
- D1/D2 后续应引用 D0。

---

## 修改 10：调整 D1 和 D2 对 D0 的依赖

位置：

修改 D1 和 D2。

### 10.1 D1 增加依赖说明

在 D1 Goal 或 Tasks 中加入：

```markdown
This task must follow D0. Store protocols should encode the persistence behavior contract instead of only matching current file-store method shapes.
```

D1 Tasks 增加：

```markdown
- Convert D0 behavior rules into store protocol method contracts.
- Add shared contract-test fixtures that can be reused for file, fake/in-memory, and SQL stores.
```

### 10.2 D2 增加依赖说明

在 D2 Goal 或 Tasks 中加入：

```markdown
This task must follow D0 and D1. SQL tables and migrations should implement the agreed store behavior contract and interfaces.
```

D2 Tasks 增加：

```markdown
- Store review versions or regeneration metadata according to D0.
- Store prompt context snapshots for auditability.
- Preserve event sequence ordering and idempotent finalization semantics.
- Run shared store contract tests in SQL mode.
```

验收：

- D1/D2 不再像独立基础设施任务，而是明确依赖行为契约。
- D2 不应先于 D0/D1 出现在短期 Sprint 中。

---

## 修改 11：增强 E3 Second Domain Spike

位置：

修改现有：

```markdown
### E3. Second Domain Spike
```

目标：

明确第二领域 Spike 的选择原则和不要过早抽象 shared packages。

### 11.1 新增 Why

```markdown
Why:
The first domain can make MR-specific concepts look platform-generic. A deliberately small but meaningfully different second domain is needed to prove which abstractions belong in shared packages and which should remain domain-owned.
```

### 11.2 扩展 Tasks

在原有 Tasks 基础上加入：

```markdown
- Prefer a domain that is conversation-based but structurally different from MR, such as customer complaint handling, internal IT helpdesk communication, sales cold call practice, or interview questioning practice.
- Keep the spike intentionally small:
  - 2 scenarios
  - 2-3 subskills
  - minimal personas
  - minimal rubric
  - minimal prompt assets
  - optional policy/compliance only if relevant
- Record which platform assumptions held and which were MR-specific.
- Identify shared package changes only after the spike is running.
- Add a short spike review document or TODO subsection summarizing required platform changes.
```

### 11.3 增强 Acceptance

```markdown
Acceptance:

- Web/Hermes can list multiple skills.
- `mr_visit_jp` behavior remains unchanged.
- The second domain satisfies the minimum runtime contract without copying MR internals.
- The spike produces a written list of proven shared abstractions and rejected premature abstractions.
```

### 11.4 增强 Do not

```markdown
Do not:

- Generalize MR-specific scoring, compliance, or visit-flow concepts before the second domain proves they are shared.
- Build a full second product.
- Add thick shared packages just to make the spike look elegant.
```

验收：

- E3 明确“第二领域用于验证抽象”。
- 明确建议可选领域。
- 明确产出 spike review。

---

## 修改 12：在 Phase H 中新增 H4 Human Evaluation Feedback Loop

位置：

在 `## 11. Phase H: Model Ops And Prompt System` 下，H3 后新增。

新增标题：

```markdown
### H4. Human Evaluation Feedback Loop
```

新增完整 ticket：

```markdown
### H4. Human Evaluation Feedback Loop

Status: [ ]

Goal:
Create a path for trainer or SME review corrections to improve evaluation fixtures, prompt profiles, and model/rule quality over time.

Why:
AI-generated judging and coaching should be schema-validated and evidence-backed, but real MR training quality eventually needs human expert calibration. SME corrections can become high-value evaluation data instead of one-off comments.

Tasks:

- Define a human review record shape for:
  - accept AI review
  - correct subskill score
  - correct diagnosis
  - correct compliance severity
  - add SME comment
  - mark evidence as sufficient or insufficient
- Decide which corrections become evaluation fixtures.
- Add export/import conventions for SME-labeled examples.
- Connect SME corrections to offline evaluation dataset lifecycle.
- Keep this as a future roadmap item until Review UX, persistence contracts, and organization roles are ready.

Acceptance:

- The roadmap explains how human trainer feedback can become evaluation data.
- SME correction does not silently mutate historical AI review without versioning.
- Future offline evaluation can compare AI output against SME gold labels.

Do not:

- Treat SME override as required for local Alpha.
- Add human review workflow before identity, roles, and review persistence are ready.
- Let human correction overwrite original AI artifacts without audit/version metadata.
```

验收：

- H4 被加入 Phase H。
- 明确它是未来路线，不是立即实现。
- 强调 audit/version，不允许静默覆盖 AI review。

---

## 修改 13：调整 Suggested Next Sprint

位置：

修改：

```markdown
## 15. Suggested Next Sprint
```

问题：

当前 Suggested Next Sprint 中包含已经完成的 Q5 和 R4，而且过早把 D2 SQL 放在 D1/D0 之前。需要重写。

请把该节替换为新的短期路线。

建议新内容：

```markdown
## 15. Suggested Next Sprints

The old immediate queue items Q0-Q5 and most Phase R/A foundation work are now complete. The next roadmap should prioritize training quality and learner-visible review value before heavy production persistence work.

### Sprint 1: Make Review And Training Quality Useful

1. B0: Training Quality Metrics Definition.
2. B1: Scenario-Specific Playbooks.
3. B2: Compliance As First-Class Training Signal.
4. C2a: Minimal Evidence Review UX.

Reason:
The system already has a working text training loop and evidence-linked review foundation. The highest-value next step is to make the learner understand what happened, why it was diagnosed that way, and what behavior to practice next.

Exit signal:
A learner can complete a session, see transcript-backed skill and compliance feedback, and understand one or two concrete next behaviors without opening raw JSON.

### Sprint 2: Turn Recommendations Into A Teaching Plan

1. B3: Coaching Continuity As A Teaching Plan.
2. B4: Recommendation Policy V2.
3. C3: Progress UX As Training Plan.
4. Expand recommendation fixtures for teaching-plan outcomes, compliance priority, and stop conditions.

Reason:
Once single-session review is useful, the next value is multi-session progression. The learner should know not only what went wrong, but what path to practice next and when to stop repeating a scenario.

Exit signal:
Progress can show a 2-3 step explainable practice path based on learner history, review evidence, compliance signals, and continuity plans.

### Sprint 3: Stabilize Runtime Contracts And Persistence Semantics

1. E2: Runtime Contract Spec.
2. D0: Persistence Behavior Contract.
3. D1: Store Interface Formalization.
4. D2: SQLModel Schema And Alembic Migrations.

Reason:
Durable storage and multi-domain readiness are important, but SQL should implement explicit behavior semantics and store interfaces rather than current file-store accidents.

Exit signal:
A future domain runtime can follow the contract, and file/SQL stores can be tested against shared behavior fixtures.

### Sprint 4: Prove Platformization With A Second Domain

1. E3: Second Domain Spike.
2. Identify shared package changes proven by the spike.
3. Add reusable runtime contract tests for the second domain.
4. Revisit H1 Prompt Builder Package only for abstractions proven by multiple domains.

Reason:
COSI should become a Skill World platform through evidence from multiple domains, not by prematurely generalizing MR-specific assumptions.

Exit signal:
Hermes/Web can list and route at least two skills, while `mr_visit_jp` behavior remains unchanged.
```

验收：

- 标题可从 `Suggested Next Sprint` 改为 `Suggested Next Sprints`。
- 不再推荐已完成 Q5/R4。
- D2 不再排在 D0/D1 前。
- 明确 Sprint 1/2 先做训练质量和 Review UX。

---

## 修改 14：更新 Phase-Level Exit Contracts

位置：

修改 `## 16. Phase-Level Exit Contracts` 中 Phase B、C、D、E、H 的 exit contracts。

### 14.1 修改 Phase B Target

现有 Phase B target 应增强为：

```markdown
Target:
Improve the pedagogical value of MR training through measurable training-quality metrics, scenario playbooks, compliance-first signals, continuity-based teaching plans, and explainable practice paths.
```

### 14.2 修改 Phase B Expected test result

加入：

```markdown
Training-quality fixtures check not only schema validity but also evidence specificity, diagnosis clarity, coaching actionability, compliance usefulness, and recommendation explainability.
```

### 14.3 修改 Phase B Acceptance standard

加入：

```markdown
The system can explain every important coaching or recommendation decision from scenario playbooks, transcript evidence, compliance rules, learner history, or teaching-plan outcomes.
```

### 14.4 修改 Phase C Target

把 Review UX 提前的思想加入：

```markdown
Target:
Make the Web app usable as a repeated training product, starting with minimal evidence-backed review clarity and then expanding into live-session polish, progress dashboard, records filtering, and replay.
```

### 14.5 修改 Phase D Target

加入 D0：

```markdown
Target:
Move from local file persistence to SQL-backed storage only after persistence behavior semantics and store interfaces are explicit, without changing public runtime/Hermes/Web behavior.
```

### 14.6 修改 Phase E Acceptance standard

加入：

```markdown
Shared package expansion is accepted only when the second-domain spike proves the abstraction is not MR-specific.
```

### 14.7 修改 Phase H Acceptance standard

加入 H4：

```markdown
Model and rule quality can be improved through fixture gates and, later, SME-labeled corrections with audit/version metadata.
```

验收：

- Phase exit contracts 反映新增 B0、D0、H4。
- Phase C 强调先做 Minimal Evidence Review UX。
- Phase E 明确 shared abstraction 需要第二领域证明。

---

# 五、最终 TODO.md 结构应大致如下

修改后，相关章节应包含这些新增或调整后的项目：

```markdown
## 0. Project Understanding

### North Star
### Three-Layer Product Architecture
### Current Baseline Already Landed
### Architecture Guardrails
### Training Role Ownership Boundaries
### Reference Review Summary
### Project Structure Review
### Standard Verification Commands

## 5. Phase B: Training Quality

### B0. Training Quality Metrics Definition
### B1. Scenario-Specific Playbooks
### B2. Compliance As First-Class Training Signal
### B3. Coaching Continuity As A Teaching Plan
### B4. Recommendation Policy V2

## 6. Phase C: Product UX And Learning Experience

### C1. Live Session UX Upgrade
### C2a. Minimal Evidence Review UX
### C2b. Advanced Transcript Linking And Replay
### C3. Progress UX As Training Plan
### C4. Records And Replay

## 7. Phase D: Production Persistence Backbone

### D0. Persistence Behavior Contract
### D1. Store Interface Formalization
### D2. SQLModel Schema And Alembic Migrations
### D3. File-To-SQL Migration Tool

## 8. Phase E: Platformization And Multi-Domain Readiness

### E1. Skill Registry Implementation
### E2. Runtime Contract Spec
### E3. Second Domain Spike

## 11. Phase H: Model Ops And Prompt System

### H1. Prompt Builder Package
### H2. OpenAI-Compatible Provider Hardening
### H3. Evaluation Dataset Lifecycle
### H4. Human Evaluation Feedback Loop

## 15. Suggested Next Sprints

Sprint 1: Make Review And Training Quality Useful
Sprint 2: Turn Recommendations Into A Teaching Plan
Sprint 3: Stabilize Runtime Contracts And Persistence Semantics
Sprint 4: Prove Platformization With A Second Domain
```

---

# 六、验收标准

本次 TODO.md 修改完成后，应满足以下验收标准：

1. TODO.md 不再推荐已完成的 Q5/R4 作为下一 Sprint。
2. Phase B 前新增 B0，明确 training quality metrics。
3. B1 playbook 被升级为教学资产，并包含 asset quality gate。
4. B2 明确 Skill Channel 和 Compliance Channel。
5. B3 明确 teaching plan snapshot/freeze/review comparison。
6. B4 明确 practice path、evidence source、stop condition。
7. C2 被拆为 C2a Minimal Evidence Review UX 和 C2b Advanced Transcript Linking And Replay。
8. D0 被加入 D1/D2 之前。
9. D1/D2 明确依赖 D0。
10. E3 明确第二领域 Spike 用于验证抽象，不能过早泛化。
11. H4 Human Evaluation Feedback Loop 被加入未来路线。
12. Project Understanding 中新增 Three-Layer Product Architecture。
13. Project Understanding 或 Architecture Guardrails 附近新增 Training Role Ownership Boundaries。
14. Phase-Level Exit Contracts 与新增内容一致。
15. TODO.md 仍保持原有执行风格：Goal / Why / Files / Tasks / Acceptance / Verification / Do not。

---

# 七、验证命令

本任务只修改 TODO.md，不需要运行完整测试。但请至少运行以下检查：

```bash
# 确认 TODO.md 中的代码块没有明显破坏 markdown fence
python - <<'PY'
from pathlib import Path
text = Path('TODO.md').read_text(encoding='utf-8')
if text.count('```') % 2 != 0:
    raise SystemExit('Unbalanced markdown code fences in TODO.md')
print('TODO.md markdown fences look balanced')
PY

# 如果仓库有 markdown lint，可运行
# pnpm markdownlint TODO.md
# 或项目已有的 docs 检查命令
```

如果项目没有 markdown lint，不要新增依赖。

---

# 八、不要做的事情

本次任务请严格避免：

- 不要实现 B0/B1/B2/B3/B4 的代码。
- 不要修改 runtime、Web、Hermes、packages 或 domain assets。
- 不要新增 SQL migration。
- 不要新增测试文件。
- 不要修改 README，除非 TODO.md 中存在明显错误引用需要同步，但本任务默认不改 README。
- 不要把 MR-specific 概念移动到 shared packages。
- 不要把 compliance 逻辑移动到 Web。
- 不要把 Doctor/Director/Judge/Coach 合并成一个大 agent。
- 不要把第二领域 Spike 写成完整产品路线。
- 不要删除原有已完成任务的历史说明。

---

# 九、建议的提交信息

建议 commit message：

```bash
docs(todo): prioritize training quality and persistence contracts
```

如果团队使用更详细的提交信息：

```bash
docs(todo): add training quality, review UX, and persistence behavior roadmap

- add training quality metrics phase item
- expand scenario playbooks into teaching assets
- clarify compliance as separate training signal
- split minimal review UX from advanced replay
- add persistence behavior contract before SQL work
- update suggested next sprints
- add human evaluation feedback loop roadmap
```

---

# 十、完成后的自检问题

提交前请回答以下问题：

1. 新路线是否优先解决“学习者是否真的知道怎么改”的问题？
2. Review UX 是否被拆成可早交付的最小版本？
3. SQL 是否被放在 D0/D1 之后，而不是直接进入 D2？
4. Recommendation 是否从单点推荐变成可解释 practice path？
5. Compliance 是否作为独立训练信号，而不是被塞进普通评分？
6. Playbook 是否能让非代码人员理解某场景到底在训练什么？
7. 第二领域 Spike 是否用于验证抽象，而不是推动过早平台化？
8. Human/SME feedback 是否作为未来质量闭环进入路线图？
9. 原有 Hermes thin 和 domain ownership 护栏是否保留？
10. 新增 ticket 是否都有可执行的 Acceptance？

如果以上任一问题答案是否定的，请继续修改 TODO.md。

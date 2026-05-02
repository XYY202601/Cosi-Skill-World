# COSI Skill World

`COSI Skill World` 是一个 AI-native 的技能训练平台仓库。它的核心目标不是先做一个通用聊天机器人，而是先做一个可诊断、可训练、可复盘、可成长追踪的 **技能成长引擎**。

当前主产品线与已落地架构 spike 是：

- `mr_visit_jp`：日文 MR 拜访训练系统
- `gp_visit_jp`：日文全科随访沟通的第二域 runtime contract spike

## 当前开发状态

当前阶段：**Alpha**

已经落地的主干能力：

- 固定 8 个日文 MR 场景，覆盖不同医生画像、时间压力、障碍类型和收尾方式
- 完整的文本训练闭环：选场景 -> 开始会话 -> 多轮对话 -> 结束 -> 复盘 -> 成长追踪
- 7 个子技能评分、结构化诊断、合规标记、下一场景推荐
- learner progress 持久化、weakness cluster 识别、coach continuity 和记忆延续
- prompt profile / experiment context / rollout gate 机制
- prompt gate 的 offline fixture + online session outcome 聚合与 promotion / blocking
- Web 端首页、场景页、训练记录列表、训练记录详情、复盘页、成长页
- 团队主管视图与只读 admin 运营 / 内容视图
- 训练记录页的 URL 状态持久化，支持刷新和分享链接后保留筛选上下文
- 合成 demo learner 数据，内置 `learner_demo_001`、`learner_demo_300`、`learner_demo_1000`
- Hermes 到 runtime 的 API proxy contract 测试，以及 runtime 自身的 session / progress / recommendation / evaluation 测试

当前明确还没做完的部分：

- 仍然是 **text-only**，没有语音、视频或实时语音陪练
- 当前用户可见主路径仍以 `mr_visit_jp` 为主，`gp_visit_jp` 只是用来验证多域架构的最小 spike，不是完整第二产品
- 默认存储还是 **本地文件持久化**，不是生产级数据库架构
- 没有完整账号体系、组织管理或权限模型；当前运营后台仍是只读视图
- 没有完整的课程编排、班组管理、排行榜、成就系统
- Hermes 目前仍保持 **thin orchestrator**，不拥有 turn-level domain logic

## 终极目标

这个仓库的终极目标不是一个“MR 训练小工具”，而是一个可扩展的 **技能世界操作系统**：

- 支持多个训练域，而不只是 MR 拜访
- 每个训练域都能拥有自己的场景、rubric、compliance、prompt contract 和 progression 模型
- 支持长期 learner memory、连续 coaching、阶段性 curriculum 和个性化推荐
- 从文本训练逐步扩展到语音、多模态、角色世界、任务地图和长期成长体系
- 从单人训练扩展到团队、主管、培训负责人可见的诊断与运营视角
- 最终形成一个“诊断 -> 训练 -> 反馈 -> 成长 -> 再训练”的闭环平台，而不是一次性问答产品

## 当前产品主路径

当前可运行的 Alpha 主路径是：

1. 在 Web 端进入首页 dashboard
2. 在场景页选择一个 MR 训练场景
3. 启动训练会话，和医生角色进行多轮文本对话
4. 结束会话后生成 review、diagnosis、subskill score、compliance signal
5. 更新 learner progress，并生成 recommendation 和 coach memory
6. 在训练记录页查看历史记录、筛选、回看详情和复盘
7. 在成长页查看阶段性训练结果和推荐方向

当前主要页面路由：

- `/`：首页 dashboard
- `/scenarios`：场景选择页
- `/records`：训练记录总览
- `/records/[id]`：单次训练记录详情
- `/records/[id]/review`：单次训练复盘页
- `/progress`：成长页
- `/team`：主管 / 团队视图
- `/admin`：运营 / 内容只读后台

## 系统架构

当前生产主干可以简单理解为：

```text
Browser
  -> apps/web (Next.js UI + route handlers)
      -> apps/hermes-orchestrator (FastAPI thin proxy, optional)
          -> apps/mr-visit-jp-runtime (FastAPI MR domain runtime)
              -> domains/mr_visit_jp (scenarios / prompts / rubrics / compliance)
              -> local file stores (.data sessions / events / progress)
          -> apps/gp-visit-jp-runtime (FastAPI GP domain spike runtime)
              -> domains/gp_visit_jp (scenarios / prompts / rubrics / compliance)
              -> in-memory spike stores
```

更具体一点：

1. `apps/web`
   负责产品界面和前端交互。
   同时通过 Next Route Handlers 提供一个很薄的前端代理层，把浏览器请求转给 Hermes 或 runtime。

2. `apps/hermes-orchestrator`
   负责平台级转发和 skill boundary。
   当前它保持很薄，只做 API proxy / skill routing，不拥有具体 MR 或 GP 对话逻辑。

3. `apps/mr-visit-jp-runtime`
   负责真正的 domain runtime。
   这里拥有 session lifecycle、state machine、director/doctor heuristics、review、progress、recommendation、continuity 和记忆等核心逻辑。

4. `apps/gp-visit-jp-runtime`
   负责第二域 spike 的最小 runtime contract 实现。
   它故意不复用 MR 的评分、持久化或 visit-flow 内核，只证明共享 skill/runtime contract 可以承载第二个训练域。

5. `domains/*`
   负责领域资产。
   包括场景定义、persona、skill model、diagnosis schema、compliance rules、prompt profiles 和 evaluation gate 配置。

6. `packages/` 与 `services/`
   这些目录代表共享抽象和长期分层方向。
   目前 Alpha 的可运行主路径仍然主要集中在 `apps/` 和 `domains/`。

## 关键架构原则

- **Hermes 必须保持薄**：不接管 MR 训练的逐轮 domain loop
- **Domain logic 必须留在 runtime**：特别是 scoring、diagnosis、director/doctor logic、compliance
- **Domain assets 必须留在 `domains/`**：不要把领域规则散落到前端或 Hermes
- **Structured outputs 必须先校验再持久化**
- **`references/` 是架构参考，不是运行时依赖**：Hermes-agent / DeepTutor 的设计可以借鉴，代码复制必须小范围、可归属、带 license/attribution，并且不能被生产路径直接 import

## 前后端框架与技术栈

### 前端

- `Next.js 15`
- `React 19`
- `TypeScript`
- Next App Router
- Next Route Handlers 作为前端代理 API 层

前端当前职责：

- 首页 dashboard、场景选择、训练记录、会话详情、复盘、成长视图
- 调用 Hermes / runtime API
- 展示 live session 和 historical review UI
- 维护列表筛选、分页、URL 状态同步等前端交互

### 后端

- `FastAPI`
- `Pydantic v2`
- `httpx`（Hermes 调 runtime）
- `PyYAML` + `jsonschema`（领域资产和 contract 校验）

当前后端分工：

- `apps/hermes-orchestrator`
  - 平台级 skill entry
  - runtime API proxy
  - 对外保留统一 skill 边界

- `apps/mr-visit-jp-runtime`
  - session start / turn / finish / review / events / progress
  - recommendation engine
  - coach continuity
  - evaluation gate service
  - state machine

- `apps/gp-visit-jp-runtime`
  - minimum runtime contract surface for the second-domain spike
  - deterministic turn / review / progress behavior
  - in-memory session, event, and learner progress state

### 模型与提示词体系

当前 runtime 支持三种 artifact 生成模式：

- `MR_RUNTIME_MODEL_MODE=mock`
  - 默认模式
  - 用确定性 mock / rule-based 输出支持 Alpha 开发与测试

- `MR_RUNTIME_MODEL_MODE=openai_compat`
  - 调用兼容 OpenAI `/chat/completions` 的模型服务
  - prompt contract 来自 `domains/mr_visit_jp/prompts/`

- `MR_RUNTIME_MODEL_MODE=disabled`
  - 跳过模型尝试，完全回退到规则逻辑

当前还支持：

- prompt profile registry
- experiment id / experiment flags
- offline + online evaluation gates
- rollout promotion / blocking

### 存储层

当前 Alpha 默认存储是本地文件：

- session artifacts
- event logs
- learner progress snapshots

默认数据目录：

- `apps/mr-visit-jp-runtime/.data/`

也可以通过环境变量覆盖：

- `MR_RUNTIME_DATA_DIR=/absolute/path`

仓库已经预留了 `sqlmodel` / `alembic` 依赖，为后续数据库演进做准备，但当前默认运行路径仍然是 file-based persistence。

### 测试与工程化

- `pytest`
- `pnpm`
- `TypeScript typecheck`
- Next production build
- Python `3.11+`

## 仓库结构

```text
apps/
  web/                    # Next.js 前端
  hermes-orchestrator/    # FastAPI 薄编排层
  mr-visit-jp-runtime/    # FastAPI 领域运行时
  gp-visit-jp-runtime/    # FastAPI 第二域 spike 运行时

domains/
  mr_visit_jp/            # 场景、persona、prompt、rubric、compliance
  gp_visit_jp/            # 第二域 spike 资产

packages/
  shared abstractions     # 共享抽象与长期分层方向

services/
  service-level docs      # session/event/progress/recommendation 方向定义

tests/
  fixtures + regression   # 跨模块 fixture 和回归测试

references/
  read-only reference repos # 架构参考，不参与运行时
```

当前最重要的产品主干目录是：

- `apps/web`
- `apps/hermes-orchestrator`
- `apps/mr-visit-jp-runtime`
- `apps/gp-visit-jp-runtime`
- `domains/mr_visit_jp`
- `domains/gp_visit_jp`

## 本地开发启动

### 1. 准备环境

推荐直接运行：

```bash
make doctor
make bootstrap
```

`make doctor` 会先做一轮只读诊断，检查：

- Python / `.venv` / editable Python 包
- Node / `pnpm` / `node_modules`
- `.env` / `.env.example` / 关键端口配置
- provider 配置是否与 `MR_RUNTIME_MODEL_MODE` 匹配
- `domains/mr_visit_jp` 领域资产能否通过校验
- 本地 `runtime` / `gp-runtime` / `Hermes` / `web` 的 PID、端口和 HTTP 健康状态

说明：

- 输出里的密钥类字段会自动脱敏
- 如果 stack 没启动，`doctor` 会给出 `make stack-up` 和日志路径，而不是直接报一串底层异常
- 当你怀疑 `bootstrap`、`stack-up` 或 `smoke-check` 有问题时，优先先跑一次 `make doctor`

只需要排查内容资产时，可以单独运行：

```bash
make validate-content
```

这个命令只检查：

- `domains/mr_visit_jp/` 下的场景与 persona 资产
- `domains/mr_visit_jp/prompts/` 下的 prompt profile 与 contract
- `domains/mr_visit_jp/prompts/evaluation_gates.yaml` 与离线 fixture gate 装配

它会返回可读的失败原因和修复提示，而不是直接吐底层堆栈。

常规初始化仍然推荐：

```bash
make bootstrap
```

这一步会自动完成：

- 校验 `pnpm` 和 `python3.11+`
- 创建 `.venv`
- 安装 `apps/mr-visit-jp-runtime`、`apps/gp-visit-jp-runtime` 与 `apps/hermes-orchestrator` 的 editable Python 依赖
- 安装 web 依赖
- 如果缺少 `.env`，自动从 `.env.example` 复制
- 预写入 demo learner 数据

如果你想手动执行，也仍然可以按下面顺序做：

```bash
cp .env.example .env
pnpm install
./.venv/bin/pip install -e packages/skill-registry -e apps/mr-visit-jp-runtime -e apps/gp-visit-jp-runtime -e apps/hermes-orchestrator
```

可选：预先写入 demo learner 数据：

```bash
make seed-mr-visit-jp
```

说明：

- `.env.example` 默认使用 `MR_RUNTIME_DEMO_SEED_MODE=manual`
- 本地可用性来自 `make bootstrap` 显式执行的 demo seed，而不是 runtime 启动时的隐式写入
- 如果你希望 runtime 启动时自动补齐 demo data，可手动设为 `MR_RUNTIME_DEMO_SEED_MODE=auto`
- 如果你希望 runtime 启动时完全不触碰 demo data，可设为 `MR_RUNTIME_DEMO_SEED_MODE=disabled`
- `make seed-mr-visit-jp -- --list-learners` 可查看内置 demo learner
- `make seed-mr-visit-jp -- --learner-id learner_demo_001` 可只刷新单个 demo learner
- `make seed-mr-visit-jp -- --append-today-sessions 25 --append-today-learner-id learner_demo_001` 可向默认 demo learner 追加 25 条“今日”测试记录

### 2. 一键启动本地联调栈

推荐直接运行：

```bash
make stack-up
```

这会在后台拉起：

- `apps/mr-visit-jp-runtime`
- `apps/gp-visit-jp-runtime`
- `apps/hermes-orchestrator`
- `apps/web`

补充说明：

- 如果 `.venv` / `node_modules` / `.env` 缺失，`stack-up` 会先自动触发 `bootstrap`
- 默认日志和 PID 会写到 `.tmp/local-stack/`
- `make stack-status` 可查看当前进程状态
- `make stack-down` 可停止这一套本地 stack
- 查看日志可直接执行：

```bash
tail -f .tmp/local-stack/runtime.log
tail -f .tmp/local-stack/gp-runtime.log
tail -f .tmp/local-stack/hermes.log
tail -f .tmp/local-stack/web.log
```

### 3. 验证最小闭环

```bash
make smoke-check
```

它会走一条真实联调路径：

- `web /api/runtime/scenarios`
- `Hermes /v1/scenarios` 与 `/v1/skills`
- `session start -> turn -> finish -> review -> progress`
- `Hermes /v1/skills/gp_visit_jp/*` 的第二域最小训练闭环

如果 Web 使用 `AUTH_MODE=mock`，`make smoke-check` 会自动用 mock 用户登录。默认用户是 `learner_demo_001`，默认密码是 `Welcome123`；需要覆盖时可以设置 `SMOKE_AUTH_USER_ID` 和 `SMOKE_AUTH_PASSWORD`。

如果默认端口已被占用，可以临时覆盖端口再联调：

```bash
WEB_PORT=3310 HERMES_PORT=8010 MR_RUNTIME_PORT=8110 GP_RUNTIME_PORT=8210 make stack-up
WEB_PORT=3310 HERMES_API_BASE=http://127.0.0.1:8010 MR_VISIT_JP_RUNTIME_BASE=http://127.0.0.1:8110 GP_VISIT_JP_RUNTIME_BASE=http://127.0.0.1:8210 make smoke-check
WEB_PORT=3310 HERMES_PORT=8010 MR_RUNTIME_PORT=8110 GP_RUNTIME_PORT=8210 make stack-down
```

### 4. 手动启动方式

如果你想分开启动，也仍然可以：

#### 启动 MR runtime

```bash
cd apps/mr-visit-jp-runtime
../../.venv/bin/python -m uvicorn main:app --app-dir src --reload --host 0.0.0.0 --port 8100
```

#### 启动 GP runtime

```bash
cd apps/gp-visit-jp-runtime
../../.venv/bin/python -m uvicorn main:app --app-dir src --reload --host 0.0.0.0 --port 8200
```

#### 启动 Hermes

```bash
cd apps/hermes-orchestrator
MR_VISIT_JP_RUNTIME_BASE=http://127.0.0.1:8100 GP_VISIT_JP_RUNTIME_BASE=http://127.0.0.1:8200 ../../.venv/bin/python -m uvicorn main:app --app-dir src --reload --host 0.0.0.0 --port 8000
```

#### 启动 Web

在仓库根目录：

```bash
pnpm dev
```

默认访问地址：

- Web: `http://127.0.0.1:3000`
- Hermes: `http://127.0.0.1:8000`
- MR Runtime: `http://127.0.0.1:8100`

说明：

- Web 默认优先请求 Hermes
- 如果 Hermes 在本地不可用，Web 代理会回退到 runtime
- root `pnpm dev` / `pnpm build` 已经包含 web cache clean，避免 `.next` 脏缓存问题

## 常用命令

```bash
# Web
pnpm dev
pnpm build
pnpm typecheck

# Demo seed
make seed-mr-visit-jp
make seed-mr-visit-jp -- --list-learners

# File -> SQL migration
make import-runtime-sql -- --dry-run
make import-runtime-sql -- --apply

# Bootstrap + smoke
make doctor
make validate-content
make bootstrap
make check-no-reference-imports
make stack-up
make stack-status
make stack-down
make smoke-check

# Runtime tests
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests
./.venv/bin/python -m pytest apps/gp-visit-jp-runtime/tests

# Hermes tests
./.venv/bin/python -m pytest apps/hermes-orchestrator/tests
```

说明：

- `apps/web` 的 `typecheck` 依赖 `.next/types`
- 如果直接运行 `pnpm --filter web typecheck` 报 `.next/types` 缺失，先执行一次 `pnpm --filter web build`
- `make check-no-reference-imports` 会检查 `apps/`, `packages/`, `services/`, `domains/` 是否错误引用 `references/`
- `make doctor` 会输出本地环境、关键配置、领域资产和 stack 健康诊断；敏感值会自动脱敏
- `make validate-content` 只做内容资产和 evaluation gate 校验，适合运营或内容改动后的快速回归
- `make smoke-check` 默认要求本地已有运行中的 Web / Hermes / MR runtime / GP runtime
- smoke check 会执行 Web auth/session 检查、MR 的默认闭环，以及 `gp_visit_jp` 的 skill-scoped 最小闭环
- `make stack-up` 默认会读取 `.env` 作为端口和 base URL 的默认值，但命令行环境变量优先级更高
- `make stack-up` / `make stack-down` 只管理这套本地 app stack，不会影响 `docker compose` 的 postgres / redis

## 目前最重要的业务能力

按今天这版 Alpha，最重要的不是“聊天能力”，而是以下几件事已经形成闭环：

- skill-based review，而不是松散聊天总结
- learner progress 和长期成长视图
- recommendation engine 和 recurring weakness cluster
- coach continuity 和记忆延续
- prompt rollout gating 和实验可控性
- 历史训练记录可检索、可筛选、可复盘

## 非目标

当前阶段我们**不**把下面这些事情当成主目标：

- 做一个开放域对话机器人
- 在 Hermes 里堆复杂 agent orchestration
- 先做很重的世界观系统再回头补训练质量
- 让前端持有权威业务状态

优先级始终是：

1. diagnosis
2. training loop
3. feedback
4. progression
5. world-building

## 全体 TODO 与开发路线

详细路线图维护在 `TODO.md`。它按照“参考项目采纳边界 -> 稳定现有 Alpha -> 抽出 registry/context/event spine -> 提升训练质量 -> 强化产品体验 -> 生产级持久化 -> 多域平台化 -> 组织运营 -> 课程与技能世界 -> 语音/多模态”的顺序拆解。

当前建议下一轮优先执行：

1. 保持 P0 验收门禁为绿色：full pytest、MR SQL mode、Web lint/typecheck/build、fixture gate、auth-aware smoke
2. 将 mock/OIDC auth 的 smoke 和 RBAC 负面测试纳入默认 CI，避免 Web、Hermes、runtime 的身份边界漂移
3. 持续跟踪 Web 依赖审计；当前 Next.js critical 已通过 15.5.15 处理，PostCSS transitive moderate 仍需等待可用的非破坏性升级路径
4. 收紧当前 ESLint baseline，把临时放宽的规则逐项恢复为 error
5. 增加 Playwright 或等价 e2e walkthrough，覆盖 marketplace、training plans、cross-skill dashboard 和 review/progress 主路径
6. 建立初始 baseline commit/tag，后续 Review 按 diff 和 CI 结果执行

## 参考目录说明

- `references/hermes-agent`
- `references/deeptutor`

这两个目录是主要架构参考和可审阅的实现样本，但不是当前运行时代码的一部分，也不应该被生产路径 import。具体采纳矩阵、license 边界、可复制代码规则和记录模板见 `docs/architecture/reference-mapping.md` 与 `docs/architecture/reference-adoption-template.md`。

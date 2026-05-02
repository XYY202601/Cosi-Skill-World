# K1: Networked Data Read Models And Environment Wiring — Progress

## Status: COMPLETE ✓

## Key Changes

### Core Design: `DEPLOY_ENV` environment variable
- Values: `development` (default), `staging`, `production`
- Controls Web fallback: only `development` allows Hermes→Runtime direct fallback
- Controls validation strictness: `staging`/`production` fail fast on missing URLs

### Modified Files

| File | Change |
|------|--------|
| `apps/web/src/lib/runtime-api.ts` | Added `DeployEnv` type, `getDeployEnv()`, `validateDeployEnv()`; cleaned `getPlatformApiBase()` to remove `RUNTIME_API_BASE` (was causing cross-contamination); gated `proxyRuntime()` fallback on `development` mode |
| `apps/hermes-orchestrator/src/runtime_proxy.py` | Added `DeployEnv` enum, `get_deploy_env()`, `validate_runtime_env()` |
| `apps/hermes-orchestrator/src/main.py` | Added startup validation (`@app.on_event("startup")` calling `validate_runtime_env()`, fails with `SystemExit(1)`); added `deploy_env` to diagnostics payload |
| `apps/web/src/app/api/local/diagnostics/route.ts` | **New** — Web diagnostics endpoint returning `deploy_env`, `hermes_api_base`, `fallback_disabled` |
| `.env.example` | Added `DEPLOY_ENV`, env var resolution rules, per-environment requirements table |
| `docs/deployment.md` | Added URL resolution order, environment requirements table, `DEPLOY_ENV` section, Networked Smoke Test section with 4 verification steps |

### Environment Variable Rules

| Variable | Used By | Required In |
|---|---|---|
| `DEPLOY_ENV` | Web, Hermes | No (default: `development`) |
| `HERMES_API_BASE` | Web | staging, production |
| `MR_VISIT_JP_RUNTIME_BASE` | Hermes | staging, production |
| `GP_VISIT_JP_RUNTIME_BASE` | Hermes | If GP skill used |

### Verification

- **pnpm typecheck**: passed
- **pnpm build**: passed, includes `/api/local/diagnostics` route
- **Hermes tests**: 3/3 passed
- **MR runtime tests (file mode)**: 53/53 passed (no regression)

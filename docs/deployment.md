# Deployment Configuration

This guide provides the necessary environment configuration details and operational plans for deploying the Cosi Skill World applications across different environments (Development, Staging, Production).

## Environment Variables

### 1. Database Configuration (Shared)
These variables are required by both `apps/hermes-orchestrator` and `apps/mr-visit-jp-runtime`.

- `POSTGRES_DB`: Name of the PostgreSQL database (default: `cosi`).
- `POSTGRES_USER`: PostgreSQL user (default: `cosi`).
- `POSTGRES_PASSWORD`: PostgreSQL password.
- `POSTGRES_URL`: Full connection string (e.g., `postgresql://user:password@host:port/db`). Keep this strictly as a secret.

### 2. Redis Configuration
Required by `apps/hermes-orchestrator`.

- `REDIS_URL`: Redis connection string (e.g., `redis://redis:6379/0`).

### 3. Application Routing
These variables define how the microservices communicate with one another.

#### URL Resolution Order

**Web -> Hermes** (inside `getPlatformApiBase()`):
1. `HERMES_API_BASE` — primary Hermes URL (required in staging/production)
2. `NEXT_PUBLIC_HERMES_API_BASE` — public Hermes URL fallback
3. Default: `http://127.0.0.1:8000`

**Hermes -> Runtime** (inside `resolve_runtime_api_base()`):
1. `<SKILL>_RUNTIME_BASE` — e.g., `MR_VISIT_JP_RUNTIME_BASE`
2. `RUNTIME_API_BASE` — generic fallback for all skills
3. Default: `http://127.0.0.1:8100` (MR only; other skills fail if unset)

#### Environment Requirements

| Variable | Development | Staging | Production |
|---|---|---|---|
| `DEPLOY_ENV` | optional (default) | required | required |
| `HERMES_API_BASE` | optional | **required** | **required** |
| `MR_VISIT_JP_RUNTIME_BASE` | optional | **required** | **required** |
| `GP_VISIT_JP_RUNTIME_BASE` | optional | required if GP used | required if GP used |

In **development** mode, the Web backend may fall back to calling the runtime directly
if Hermes is unreachable. In **staging** and **production**, this fallback is disabled —
all runtime-bound traffic must go through Hermes. Missing required variables cause an
immediate startup failure.

### 4. Deployment Environment (`DEPLOY_ENV`)

Set `DEPLOY_ENV` to one of `development`, `staging`, or `production`:

- **development** (default): No validation; localhost defaults allowed.
- **staging**: Validates that `HERMES_API_BASE` and `<SKILL>_RUNTIME_BASE` are configured.
  Failover to direct runtime is disabled.
- **production**: Same as staging, but with stricter assumptions for production-grade deployments.

### 5. Networked Smoke Test

After deploying Web, Hermes, and Runtime on non-localhost hosts (Docker, Kubernetes, etc.):

**1. Validate Hermes can reach its runtime:**
```bash
curl -s http://<hermes-host>:8000/healthz | jq .
```
Expected: `runtime_api_base` matches the Runtime URL, `deploy_env` matches your setting.

**2. Validate Web can reach Hermes:**
```bash
curl -s http://<web-host>:3000/api/local/diagnostics | jq .
```
Expected: `deploy_env` matches your setting, `hermes_api_base` matches the Hermes URL,
`fallback_disabled` is `true` for staging/production.

**3. End-to-end scenario fetch through the full chain:**
```bash
curl -s http://<web-host>:3000/api/runtime/scenarios | jq '.scenario_count'
```
Expected: a positive integer. Validates Web -> Hermes -> Runtime.

**4. Verify production validation fails fast:**
```bash
DEPLOY_ENV=production HERMES_API_BASE= pnpm start
```
Expected: startup error about missing `HERMES_API_BASE`, not a silent fallback.

**URL Resolution Diagram (production):**
```
Browser --> Web (Next.js) --> Hermes Orchestrator --> Runtime
           /api/runtime/*      HERMES_API_BASE        MR_VISIT_JP_RUNTIME_BASE
           (no fallback)                               (or RUNTIME_API_BASE)
```

## Health Checks

For deployment targets like Kubernetes or AWS ECS, configure the following liveness and readiness probes:

- **Hermes Orchestrator**: `GET /healthz` (Port 8000)
- **MR Visit JP Runtime**: `GET /healthz` (Port 8100)

These endpoints verify internal application state and database connectivity.

## Backup and Restore Plan

Before moving to production, ensure the database is backed up regularly. 

### Backup
Create a scheduled job (e.g., a cron job or an AWS RDS backup policy) to run:
```bash
pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -F c -f /backup/db_backup_$(date +%F).dump
```

### Restore
To restore in case of failure or for syncing staging with production:
```bash
pg_restore -U $POSTGRES_USER -d $POSTGRES_DB -1 /backup/db_backup.dump
```

## Security Best Practices
- **Separation of Secrets**: Do not commit passwords or API keys to version control. Use a secret manager (AWS Secrets Manager, GitHub Secrets, HashiCorp Vault) to inject them at runtime.
- **Network Boundaries**: Only the `apps/web` container needs public internet exposure. `hermes`, `runtime`, `postgres`, and `redis` should be isolated in private subnets.

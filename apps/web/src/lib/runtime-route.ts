import { createHash, randomUUID } from "node:crypto";

import { NextRequest, NextResponse } from "next/server";

import {
  canAccessLearner,
  canViewAdminOperations,
  canViewTeam,
  canViewOrganizationReports,
  getAuthMode,
  getServerSession,
  type SessionUser,
} from "@/lib/auth";
import {
  proxyRuntime,
  type RuntimeProxyResult,
  type TraceResponseHeader,
} from "@/lib/runtime-api";

const SERVICE_NAME = "web-runtime-proxy";
const MOCK_AUTH_DEFAULT_ORG_ID = "local";
const PUBLIC_RUNTIME_ACTIONS = new Set(["list_scenarios"]);
const UNSCOPED_ORG_IDS = new Set(["all", "default", "global", "local", "unscoped"]);

type ProxyRouteOptions = {
  actionId: string;
  path: string;
  method: "GET" | "POST" | "DELETE";
  body?: unknown;
  learnerId?: string;
  sessionId?: string;
};

type RequestTraceContext = {
  actionId: string;
  experimentId?: string;
  learnerHash?: string;
  method: string;
  path: string;
  promptProfile?: string;
  requestId: string;
  serviceName: string;
  sessionId?: string;
  traceId: string;
  turnId?: string;
  upstreamBase?: string;
  upstreamServiceName?: string;
};

function normalizeString(value: string | null | undefined): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  const normalized = value.trim();
  return normalized || undefined;
}

function createTraceId(prefix: string): string {
  return `${prefix}_${randomUUID().replace(/-/g, "").slice(0, 12)}`;
}

function hashIdentifier(value: string | undefined): string | undefined {
  const normalized = normalizeString(value);
  if (!normalized) {
    return undefined;
  }
  return createHash("sha256").update(normalized).digest("hex").slice(0, 12);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function bindPayloadMetadata(
  context: RequestTraceContext,
  payload: unknown
): void {
  if (!isRecord(payload)) {
    return;
  }
  const sessionId = normalizeString(
    typeof payload.session_id === "string" ? payload.session_id : undefined
  );
  if (sessionId) {
    context.sessionId = sessionId;
  }

  const experimentContext = payload.experiment_context;
  if (!isRecord(experimentContext)) {
    return;
  }

  const promptProfile = normalizeString(
    typeof experimentContext.profile_id === "string"
      ? experimentContext.profile_id
      : undefined
  );
  const experimentId = normalizeString(
    typeof experimentContext.experiment_id === "string"
      ? experimentContext.experiment_id
      : undefined
  );

  if (promptProfile) {
    context.promptProfile = promptProfile;
  }
  if (experimentId) {
    context.experimentId = experimentId;
  }
}

function bindTraceHeaders(
  context: RequestTraceContext,
  headers: Partial<Record<TraceResponseHeader, string>>
): void {
  const traceId = normalizeString(headers["x-trace-id"]);
  const sessionId = normalizeString(headers["x-session-id"]);
  const turnId = normalizeString(headers["x-turn-id"]);
  const upstreamServiceName = normalizeString(headers["x-service-name"]);

  if (traceId) {
    context.traceId = traceId;
  }
  if (sessionId) {
    context.sessionId = sessionId;
  }
  if (turnId) {
    context.turnId = turnId;
  }
  if (upstreamServiceName) {
    context.upstreamServiceName = upstreamServiceName;
  }
}

function resolveForwardedHeader(
  request: NextRequest,
  headerName: string,
  queryParam: string
): string | undefined {
  return (
    normalizeString(request.headers.get(headerName)) ??
    normalizeString(request.nextUrl.searchParams.get(queryParam))
  );
}

async function buildForwardHeaders(
  request: NextRequest,
  context: RequestTraceContext,
  session?: SessionUser | null
): Promise<Headers> {
  const headers = new Headers();
  headers.set("x-request-id", context.requestId);
  headers.set("x-trace-id", context.traceId);
  if (context.sessionId) {
    headers.set("x-session-id", context.sessionId);
  }
  if (context.turnId) {
    headers.set("x-turn-id", context.turnId);
  }

  if (getAuthMode() === "mock" || getAuthMode() === "oidc") {
    // When AUTH_MODE=mock or oidc, identity comes from the server-side session.
    // Client-supplied query params / headers are NOT trusted.
    const activeSession = session ?? await getServerSession();
    if (activeSession) {
      const requestedOrg = resolveForwardedHeader(request, "x-org-id", "org");
      const normalizedRequestedOrg = requestedOrg?.trim().toLowerCase();
      const requestedUnscopedOrg =
        typeof normalizedRequestedOrg === "string" &&
        UNSCOPED_ORG_IDS.has(normalizedRequestedOrg);
      const canOverrideOrgScope =
        canViewTeam(activeSession) ||
        canViewOrganizationReports(activeSession) ||
        canViewAdminOperations(activeSession);
      if (requestedOrg && canOverrideOrgScope) {
        if (!requestedUnscopedOrg) {
          headers.set("x-org-id", requestedOrg);
        }
      } else if (activeSession.org_id) {
        headers.set("x-org-id", activeSession.org_id);
      } else if (!requestedUnscopedOrg && (process.env.MR_RUNTIME_AUTH_MODE || "disabled").trim().toLowerCase() === "enabled") {
        headers.set("x-org-id", MOCK_AUTH_DEFAULT_ORG_ID);
      }
      headers.set("x-viewer-role", activeSession.role);
      headers.set("x-auth-user", activeSession.learner_id);
    }
  } else {
    // When AUTH_MODE=disabled, forward identity from query params / request headers.
    const orgId = resolveForwardedHeader(request, "x-org-id", "org");
    if (orgId) {
      headers.set("x-org-id", orgId);
    }
    const viewerRole = resolveForwardedHeader(request, "x-viewer-role", "viewer");
    if (viewerRole) {
      headers.set("x-viewer-role", viewerRole);
    }
  }
  return headers;
}

function applyResponseHeaders(
  response: NextResponse,
  context: RequestTraceContext
): void {
  response.headers.set("x-request-id", context.requestId);
  response.headers.set("x-trace-id", context.traceId);
  response.headers.set("x-service-name", context.serviceName);
  if (context.sessionId) {
    response.headers.set("x-session-id", context.sessionId);
  }
  if (context.turnId) {
    response.headers.set("x-turn-id", context.turnId);
  }
}

function isBodylessStatus(statusCode: number): boolean {
  return statusCode === 204 || statusCode === 205 || statusCode === 304;
}

function logProxyResult(
  context: RequestTraceContext,
  options: {
    statusCode: number;
    durationMs: number;
    error?: string;
  }
): void {
  const { statusCode, durationMs, error } = options;
  const payload: Record<string, number | string> = {
    action_id: context.actionId,
    duration_ms: Number(durationMs.toFixed(2)),
    event: "http.request",
    method: context.method,
    path: context.path,
    request_id: context.requestId,
    service_name: context.serviceName,
    status_code: statusCode,
    trace_id: context.traceId,
  };

  if (context.sessionId) {
    payload.session_id = context.sessionId;
  }
  if (context.turnId) {
    payload.turn_id = context.turnId;
  }
  if (context.learnerHash) {
    payload.learner_hash = context.learnerHash;
  }
  if (context.promptProfile) {
    payload.prompt_profile = context.promptProfile;
  }
  if (context.experimentId) {
    payload.experiment_id = context.experimentId;
  }
  if (context.upstreamBase) {
    payload.upstream_base = context.upstreamBase;
  }
  if (context.upstreamServiceName) {
    payload.upstream_service_name = context.upstreamServiceName;
  }
  if (error) {
    payload.error = error.slice(0, 160);
  }

  const logger = statusCode >= 500 ? console.error : statusCode >= 400 ? console.warn : console.info;
  logger(JSON.stringify(payload));
}

function buildRequestTraceContext(
  request: NextRequest,
  options: ProxyRouteOptions
): RequestTraceContext {
  return {
    actionId: options.actionId,
    learnerHash: hashIdentifier(options.learnerId),
    method: options.method,
    path: request.nextUrl.pathname,
    requestId: normalizeString(request.headers.get("x-request-id")) ?? createTraceId("req"),
    serviceName: SERVICE_NAME,
    sessionId: normalizeString(options.sessionId),
    traceId: normalizeString(request.headers.get("x-trace-id")) ?? createTraceId("trace"),
  };
}

function stringifyBody(body: unknown): string | undefined {
  if (body === undefined) {
    return undefined;
  }
  return JSON.stringify(body);
}

function authErrorResponse(
  context: RequestTraceContext,
  startedAt: number,
  statusCode: 401 | 403,
  detail: string
): NextResponse {
  const response = NextResponse.json({ detail }, { status: statusCode });
  applyResponseHeaders(response, context);
  logProxyResult(context, {
    statusCode,
    durationMs: performance.now() - startedAt,
    error: detail,
  });
  return response;
}

async function prepareMockRuntimeRequest(
  options: ProxyRouteOptions,
  context: RequestTraceContext,
  startedAt: number
): Promise<
  | { ok: true; session: SessionUser | null; body: unknown }
  | { ok: false; response: NextResponse }
> {
  if (getAuthMode() !== "mock" && getAuthMode() !== "oidc") {
    return { ok: true, session: null, body: options.body };
  }

  const session = await getServerSession();
  if (!session && !PUBLIC_RUNTIME_ACTIONS.has(options.actionId)) {
    return {
      ok: false,
      response: authErrorResponse(
        context,
        startedAt,
        401,
        "Authentication required. Please log in.",
      ),
    };
  }

  if (!session) {
    return { ok: true, session: null, body: options.body };
  }

  if (options.learnerId && !canAccessLearner(session, options.learnerId)) {
    return {
      ok: false,
      response: authErrorResponse(
        context,
        startedAt,
        403,
        "Learners can only access their own training data.",
      ),
    };
  }

  let body = options.body;
  if (options.actionId === "start_session") {
    if (!isRecord(body)) {
      return {
        ok: false,
        response: authErrorResponse(
          context,
          startedAt,
          403,
          "Start session requires a valid learner identity.",
        ),
      };
    }
    const requestedLearnerId = normalizeString(
      typeof body.learner_id === "string" ? body.learner_id : undefined
    );
    const effectiveLearnerId = requestedLearnerId ?? session.learner_id;
    if (!canAccessLearner(session, effectiveLearnerId)) {
      return {
        ok: false,
        response: authErrorResponse(
          context,
          startedAt,
          403,
          "Learners can only start sessions for themselves.",
        ),
      };
    }
    if (!requestedLearnerId) {
      body = { ...body, learner_id: session.learner_id };
    }
  }

  if (
    options.actionId === "get_training_plan_progress" &&
    !canViewOrganizationReports(session) &&
    !canViewAdminOperations(session)
  ) {
    return {
      ok: false,
      response: authErrorResponse(
        context,
        startedAt,
        403,
        "Plan progress requires supervisor or administrator access.",
      ),
    };
  }

  if (
    options.actionId === "get_organization_reports" &&
    !canViewOrganizationReports(session)
  ) {
    return {
      ok: false,
      response: authErrorResponse(
        context,
        startedAt,
        403,
        "Organization reports require supervisor or administrator access.",
      ),
    };
  }

  if (
    ["get_evaluation_gates", "list_training_plans", "create_training_plan",
     "get_training_plan", "update_training_plan", "delete_training_plan",
     "assign_learners", "unassign_learners"].includes(options.actionId) &&
    !canViewAdminOperations(session)
  ) {
    return {
      ok: false,
      response: authErrorResponse(
        context,
        startedAt,
        403,
        "Admin operations require an administrator role.",
      ),
    };
  }

  return { ok: true, session, body };
}

export async function proxyRuntimeRoute(
  request: NextRequest,
  options: ProxyRouteOptions
): Promise<NextResponse> {
  const context = buildRequestTraceContext(request, options);
  const startedAt = performance.now();

  try {
    const prepared = await prepareMockRuntimeRequest(options, context, startedAt);
    if (!prepared.ok) {
      return prepared.response;
    }

    const result: RuntimeProxyResult = await proxyRuntime(options.path, {
      method: options.method,
      body: stringifyBody(prepared.body),
      headers: await buildForwardHeaders(request, context, prepared.session),
    });

    bindTraceHeaders(context, result.headers);
    bindPayloadMetadata(context, result.payload);
    context.upstreamBase = result.upstreamBase;

    const response = isBodylessStatus(result.status)
      ? new NextResponse(null, { status: result.status })
      : NextResponse.json(result.payload, { status: result.status });
    applyResponseHeaders(response, context);
    logProxyResult(context, {
      statusCode: result.status,
      durationMs: performance.now() - startedAt,
    });
    return response;
  } catch (error) {
    logProxyResult(context, {
      statusCode: 500,
      durationMs: performance.now() - startedAt,
      error: error instanceof Error ? error.message : "runtime proxy failure",
    });
    throw error;
  }
}

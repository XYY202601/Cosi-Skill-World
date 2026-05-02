import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function GET(request: NextRequest, context: RouteContext) {
  const resolvedParams = await context.params;
  return proxyRuntimeRoute(request, {
    actionId: "get_session_events",
    path: `/v1/sessions/${resolvedParams.id}/events`,
    method: "GET",
    sessionId: resolvedParams.id,
  });
}

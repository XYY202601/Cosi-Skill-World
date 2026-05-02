import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function GET(request: NextRequest, context: RouteContext) {
  const resolvedParams = await context.params;
  return proxyRuntimeRoute(request, {
    actionId: "get_session",
    path: `/v1/sessions/${resolvedParams.id}`,
    method: "GET",
    sessionId: resolvedParams.id,
  });
}

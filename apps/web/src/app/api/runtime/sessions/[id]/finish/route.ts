import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function POST(request: NextRequest, context: RouteContext) {
  const resolvedParams = await context.params;
  return proxyRuntimeRoute(request, {
    actionId: "finish_session",
    path: `/v1/sessions/${resolvedParams.id}/finish`,
    method: "POST",
    sessionId: resolvedParams.id,
  });
}

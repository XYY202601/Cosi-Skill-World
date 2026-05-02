import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function POST(request: NextRequest, context: RouteContext) {
  const resolvedParams = await context.params;
  const body = await request.json();
  return proxyRuntimeRoute(request, {
    actionId: "send_turn",
    path: `/v1/sessions/${resolvedParams.id}/turn`,
    method: "POST",
    body,
    sessionId: resolvedParams.id,
  });
}

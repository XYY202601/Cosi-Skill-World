import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = await request.json();
  return proxyRuntimeRoute(request, {
    actionId: "start_session",
    path: "/v1/sessions/start",
    method: "POST",
    body,
    learnerId: typeof body?.learner_id === "string" ? body.learner_id : undefined,
  });
}

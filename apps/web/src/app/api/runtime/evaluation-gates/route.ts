import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return proxyRuntimeRoute(request, {
    actionId: "get_evaluation_gates",
    path: "/v1/evaluation-gates",
    method: "GET",
  });
}

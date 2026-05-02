import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return proxyRuntimeRoute(request, {
    actionId: "list_scenarios",
    path: "/v1/scenarios",
    method: "GET",
  });
}

import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.toString();
  const path = `/v1/marketplace${query ? `?${query}` : ""}`;
  return proxyRuntimeRoute(request, {
    actionId: "list_marketplace_skills",
    path,
    method: "GET",
  });
}

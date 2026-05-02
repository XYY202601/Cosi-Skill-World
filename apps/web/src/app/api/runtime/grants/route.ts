import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return proxyRuntimeRoute(request, {
    actionId: "list_sharing_grants",
    path: "/v1/grants",
    method: "GET",
  });
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  return proxyRuntimeRoute(request, {
    actionId: "create_sharing_grant",
    path: "/v1/grants",
    method: "POST",
    body,
  });
}

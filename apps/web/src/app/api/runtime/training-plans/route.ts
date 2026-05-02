import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return proxyRuntimeRoute(request, {
    actionId: "list_training_plans",
    path: `/v1/training-plans${request.nextUrl.search}`,
    method: "GET",
  });
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  return proxyRuntimeRoute(request, {
    actionId: "create_training_plan",
    path: "/v1/training-plans",
    method: "POST",
    body,
  });
}

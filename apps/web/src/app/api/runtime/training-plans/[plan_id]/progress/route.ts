import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

type RouteParams = {
  params: Promise<{ plan_id: string }>;
};

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { plan_id } = await params;
  return proxyRuntimeRoute(request, {
    actionId: "get_training_plan_progress",
    path: `/v1/training-plans/${encodeURIComponent(plan_id)}/progress`,
    method: "GET",
  });
}

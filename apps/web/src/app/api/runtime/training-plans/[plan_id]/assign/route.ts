import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

type RouteParams = {
  params: Promise<{ plan_id: string }>;
};

export async function POST(request: NextRequest, { params }: RouteParams) {
  const { plan_id } = await params;
  const body = await request.json().catch(() => ({}));
  return proxyRuntimeRoute(request, {
    actionId: "assign_learners",
    path: `/v1/training-plans/${encodeURIComponent(plan_id)}/assign`,
    method: "POST",
    body,
  });
}

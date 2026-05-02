import { NextRequest, NextResponse } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";
import { proxyRuntime } from "@/lib/runtime-api";

export const dynamic = "force-dynamic";

type RouteParams = {
  params: Promise<{ plan_id: string }>;
};

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { plan_id } = await params;
  return proxyRuntimeRoute(request, {
    actionId: "get_training_plan",
    path: `/v1/training-plans/${encodeURIComponent(plan_id)}`,
    method: "GET",
  });
}

export async function PUT(request: NextRequest, { params }: RouteParams) {
  const { plan_id } = await params;
  const body = await request.json().catch(() => ({}));
  return proxyRuntimeRoute(request, {
    actionId: "update_training_plan",
    path: `/v1/training-plans/${encodeURIComponent(plan_id)}`,
    method: "POST",
    body,
  });
}

export async function DELETE(request: NextRequest, { params }: RouteParams) {
  const { plan_id } = await params;
  // proxyRuntimeRoute only supports GET|POST, so use proxyRuntime directly
  const path = `/v1/training-plans/${encodeURIComponent(plan_id)}`;
  const result = await proxyRuntime(path, { method: "DELETE" });
  const response = NextResponse.json(result.payload, { status: result.status });
  return response;
}

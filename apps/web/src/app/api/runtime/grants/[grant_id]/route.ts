import { NextRequest, NextResponse } from "next/server";

import { proxyRuntime } from "@/lib/runtime-api";

export const dynamic = "force-dynamic";

type RouteParams = {
  params: Promise<{ grant_id: string }>;
};

export async function DELETE(request: NextRequest, { params }: RouteParams) {
  const { grant_id } = await params;
  // proxyRuntimeRoute only supports GET|POST, so use proxyRuntime directly
  const path = `/v1/grants/${encodeURIComponent(grant_id)}`;
  const result = await proxyRuntime(path, { method: "DELETE" });
  return NextResponse.json(result.payload, { status: result.status });
}

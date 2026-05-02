import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ org_id: string }> }
) {
  const { org_id } = await params;
  const { searchParams } = new URL(request.url);
  const stateParam = searchParams.get("state");
  const qs = stateParam ? `?state=${encodeURIComponent(stateParam)}` : "";
  return proxyRuntimeRoute(request, {
    actionId: "list_org_skills",
    path: `/v1/marketplace/org/${encodeURIComponent(org_id)}/skills${qs}`,
    method: "GET",
  });
}

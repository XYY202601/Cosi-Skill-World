import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ org_id: string }> }
) {
  const { org_id } = await params;
  const { searchParams } = new URL(request.url);
  const learnerId = searchParams.get("learner_id");
  let path = `/v1/marketplace/org/${encodeURIComponent(org_id)}/dashboard`;
  if (learnerId) {
    path += `?learner_id=${encodeURIComponent(learnerId)}`;
  }
  return proxyRuntimeRoute(request, {
    actionId: "get_marketplace_dashboard",
    path,
    method: "GET",
  });
}

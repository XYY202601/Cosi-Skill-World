import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ org_id: string; skill_id: string }> }
) {
  const { org_id, skill_id } = await params;
  const body = await request.json().catch(() => ({}));
  const path = `/v1/marketplace/org/${encodeURIComponent(org_id)}/skills/${encodeURIComponent(skill_id)}/state`;
  return proxyRuntimeRoute(request, {
    actionId: "set_org_skill_state",
    path,
    method: "POST",
    body,
  });
}

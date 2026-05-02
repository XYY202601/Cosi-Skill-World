import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ org_id: string; skill_id: string }> }
) {
  const { org_id, skill_id } = await params;
  const path = `/v1/marketplace/org/${encodeURIComponent(org_id)}/skills/${encodeURIComponent(skill_id)}`;
  return proxyRuntimeRoute(request, {
    actionId: "remove_org_skill",
    path,
    method: "DELETE",
  });
}

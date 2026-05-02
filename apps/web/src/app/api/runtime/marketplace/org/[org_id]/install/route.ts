import { NextRequest } from "next/server";

import { proxyRuntimeRoute } from "@/lib/runtime-route";

export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ org_id: string }> }
) {
  const { org_id } = await params;
  const body = await request.json().catch(() => ({}));
  const path = `/v1/marketplace/org/${encodeURIComponent(org_id)}/install`;
  return proxyRuntimeRoute(request, {
    actionId: "install_org_skill",
    path,
    method: "POST",
    body,
  });
}

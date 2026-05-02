import { NextResponse } from "next/server";

import { getAuthMode, getServerSession } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET() {
  const authMode = getAuthMode();
  const session = await getServerSession();

  if (!session) {
    return NextResponse.json({
      authenticated: false,
      auth_mode: authMode,
      user: null,
    });
  }

  return NextResponse.json({
    authenticated: true,
    auth_mode: authMode,
    user: {
      learner_id: session.learner_id,
      org_id: session.org_id,
      role: session.role,
      name: session.name,
    },
  });
}

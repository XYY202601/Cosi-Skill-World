import { NextRequest, NextResponse } from "next/server";

import {
  authenticateMockUser,
  createSession,
  getAuthMode,
  verifyPassword,
} from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const authMode = getAuthMode();
  if (authMode === "disabled") {
    return NextResponse.json(
      { detail: "Auth is disabled. Set AUTH_MODE=mock or oidc to enable." },
      { status: 403 },
    );
  }

  if (authMode === "oidc") {
    return NextResponse.json(
      { detail: "OIDC login — redirect to /api/auth/oidc/login", redirect: "/api/auth/oidc/login" },
      { status: 200 },
    );
  }

  const body = (await request.json().catch(() => null)) as Record<
    string,
    unknown
  > | null;
  const userId =
    typeof body?.user_id === "string"
      ? body.user_id
      : typeof body?.username === "string"
        ? body.username
        : null;

  if (!userId) {
    return NextResponse.json(
      { detail: "user_id is required" },
      { status: 400 },
    );
  }

  const password =
    typeof body?.password === "string" ? body.password : "";
  if (!password || !verifyPassword(password)) {
    return NextResponse.json(
      { detail: "Invalid password" },
      { status: 401 },
    );
  }

  const user = authenticateMockUser(userId);
  if (!user) {
    return NextResponse.json(
      { detail: `Unknown user: ${userId}` },
      { status: 401 },
    );
  }

  await createSession(user);

  return NextResponse.json({
    status: "ok",
    auth_mode: authMode,
    user: {
      learner_id: user.learner_id,
      org_id: user.org_id,
      role: user.role,
      name: user.name,
    },
  });
}

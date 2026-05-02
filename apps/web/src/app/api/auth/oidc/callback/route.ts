import { NextRequest, NextResponse } from "next/server";
import { handleOidcCallback, isOidcConfigured } from "@/lib/oidc";

export async function GET(request: NextRequest): Promise<NextResponse> {
  if (!isOidcConfigured()) {
    return NextResponse.json(
      { detail: "OIDC is not configured." },
      { status: 503 },
    );
  }

  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const state = searchParams.get("state");
  const error = searchParams.get("error");

  if (error) {
    const description = searchParams.get("error_description") || error;
    return NextResponse.json(
      { detail: `OIDC authorization error: ${description}` },
      { status: 400 },
    );
  }

  if (!code || !state) {
    return NextResponse.json(
      { detail: "Missing code or state parameter" },
      { status: 400 },
    );
  }

  try {
    await handleOidcCallback(code, state);
    // Redirect to home page after successful login
    return NextResponse.redirect(new URL("/", request.url));
  } catch (err) {
    const message = err instanceof Error ? err.message : "OIDC callback failed";
    return NextResponse.json({ detail: message }, { status: 500 });
  }
}

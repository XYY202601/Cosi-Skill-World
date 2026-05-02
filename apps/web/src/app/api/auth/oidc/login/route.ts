import { NextResponse } from "next/server";
import { getOidcAuthorizationUrl, isOidcConfigured } from "@/lib/oidc";

export async function GET(): Promise<NextResponse> {
  if (!isOidcConfigured()) {
    return NextResponse.json(
      { detail: "OIDC is not configured. Set OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET." },
      { status: 503 },
    );
  }

  try {
    const { url } = await getOidcAuthorizationUrl();
    return NextResponse.redirect(url);
  } catch (error) {
    const message = error instanceof Error ? error.message : "OIDC authorization failed";
    return NextResponse.json({ detail: message }, { status: 500 });
  }
}

import { cookies } from "next/headers";
import type { SessionUser } from "@/lib/mock-users";

// Re-export SessionUser type
export type { SessionUser } from "@/lib/mock-users";

// ── OIDC configuration from environment ─────────────────────────────

interface OidcConfig {
  issuer: string;
  clientId: string;
  clientSecret: string;
  redirectUri: string;
  learnerIdClaim: string;
  orgIdClaim: string;
  roleClaim: string;
}

function getOidcConfig(): OidcConfig {
  return {
    issuer: process.env.OIDC_ISSUER || "",
    clientId: process.env.OIDC_CLIENT_ID || "",
    clientSecret: process.env.OIDC_CLIENT_SECRET || "",
    redirectUri: process.env.OIDC_REDIRECT_URI || "http://localhost:3000/api/auth/oidc/callback",
    learnerIdClaim: process.env.OIDC_LEARNER_ID_CLAIM || "sub",
    orgIdClaim: process.env.OIDC_ORG_ID_CLAIM || "org_id",
    roleClaim: process.env.OIDC_ROLE_CLAIM || "roles",
  };
}

export function isOidcConfigured(): boolean {
  const config = getOidcConfig();
  return Boolean(config.issuer && config.clientId && config.clientSecret);
}

function getClaimValue(claims: Record<string, unknown>, claimPath: string): string | undefined {
  const parts = claimPath.split(".");
  let current: unknown = claims;
  for (const part of parts) {
    if (typeof current !== "object" || current === null) return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  if (typeof current === "string") return current;
  if (Array.isArray(current) && current.length > 0 && typeof current[0] === "string") {
    return current[0];
  }
  return undefined;
}

// ── Token cookie helpers ────────────────────────────────────────────

const OIDC_STATE_COOKIE = "oidc_state";
const OIDC_CODE_VERIFIER_COOKIE = "oidc_code_verifier";
const OIDC_ID_TOKEN_COOKIE = "oidc_id_token";
const OIDC_REFRESH_TOKEN_COOKIE = "oidc_refresh_token";
const OIDC_SESSION_COOKIE = "oidc_session";
const TOKEN_MAX_AGE_SEC = 86400; // 24 hours

// ── OIDC Discovery ──────────────────────────────────────────────────

interface OidcDiscovery {
  authorizationEndpoint: string;
  tokenEndpoint: string;
  userinfoEndpoint: string;
  endSessionEndpoint?: string;
}

async function discoverOidc(issuer: string): Promise<OidcDiscovery> {
  const url = `${issuer.replace(/\/$/, "")}/.well-known/openid-configuration`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`OIDC discovery failed for issuer ${issuer}: ${response.status}`);
  }
  const config = await response.json();
  if (!config.authorization_endpoint || !config.token_endpoint) {
    throw new Error(`Invalid OIDC discovery response from ${issuer}`);
  }
  return {
    authorizationEndpoint: config.authorization_endpoint,
    tokenEndpoint: config.token_endpoint,
    userinfoEndpoint: config.userinfo_endpoint,
    endSessionEndpoint: config.end_session_endpoint,
  };
}

// ── PKCE helpers ────────────────────────────────────────────────────

function generateCodeVerifier(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return Buffer.from(array).toString("base64url").replace(/=+$/, "");
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return Buffer.from(hash).toString("base64url").replace(/=+$/, "");
}

// ── Authorization URL ───────────────────────────────────────────────

export async function getOidcAuthorizationUrl(): Promise<{ url: string; state: string }> {
  const config = getOidcConfig();
  if (!isOidcConfigured()) {
    throw new Error("OIDC is not configured");
  }

  const discovery = await discoverOidc(config.issuer);
  const state = generateCodeVerifier();
  const codeVerifier = generateCodeVerifier();
  const codeChallenge = await generateCodeChallenge(codeVerifier);

  const params = new URLSearchParams({
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    response_type: "code",
    scope: "openid profile email",
    state,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
  });

  const cookieStore = await cookies();
  cookieStore.set(OIDC_STATE_COOKIE, state, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 600, // 10 minutes
    path: "/",
  });
  cookieStore.set(OIDC_CODE_VERIFIER_COOKIE, codeVerifier, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 600,
    path: "/",
  });

  return { url: `${discovery.authorizationEndpoint}?${params.toString()}`, state };
}

// ── Callback handler ────────────────────────────────────────────────

export async function handleOidcCallback(
  code: string,
  state: string,
): Promise<SessionUser> {
  const config = getOidcConfig();
  if (!isOidcConfigured()) {
    throw new Error("OIDC is not configured");
  }

  const cookieStore = await cookies();

  // Validate state
  const storedState = cookieStore.get(OIDC_STATE_COOKIE)?.value;
  if (!storedState || storedState !== state) {
    throw new Error("OIDC state mismatch — possible CSRF attack");
  }

  const codeVerifier = cookieStore.get(OIDC_CODE_VERIFIER_COOKIE)?.value;
  if (!codeVerifier) {
    throw new Error("Missing PKCE code verifier");
  }

  // Clean up state cookies
  cookieStore.delete(OIDC_STATE_COOKIE);
  cookieStore.delete(OIDC_CODE_VERIFIER_COOKIE);

  // Exchange code for tokens
  const discovery = await discoverOidc(config.issuer);
  const tokenResponse = await fetch(discovery.tokenEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: config.redirectUri,
      client_id: config.clientId,
      client_secret: config.clientSecret,
      code_verifier: codeVerifier,
    }),
  });

  if (!tokenResponse.ok) {
    const errorBody = await tokenResponse.text();
    throw new Error(`OIDC token exchange failed: ${tokenResponse.status} — ${errorBody}`);
  }

  const tokens = await tokenResponse.json();
  if (!tokens.id_token) {
    throw new Error("No id_token in OIDC token response");
  }

  // Parse ID token (simple base64 decode of the payload)
  const idTokenParts = tokens.id_token.split(".");
  if (idTokenParts.length !== 3) {
    throw new Error("Invalid ID token format");
  }
  const claims = JSON.parse(
    Buffer.from(idTokenParts[1], "base64url").toString("utf-8"),
  );

  // Extract identity from claims
  const learnerId = getClaimValue(claims, config.learnerIdClaim);
  if (!learnerId) {
    throw new Error(
      `OIDC claim "${config.learnerIdClaim}" not found in ID token. ` +
      `Available claims: ${Object.keys(claims).join(", ")}`,
    );
  }

  const orgId = getClaimValue(claims, config.orgIdClaim) || "";
  const role = getClaimValue(claims, config.roleClaim) || "learner";

  const sessionUser: SessionUser = {
    learner_id: learnerId,
    org_id: orgId,
    role,
    name: getClaimValue(claims, "name") || getClaimValue(claims, "preferred_username") || learnerId,
  };

  // Store tokens in HttpOnly cookies
  cookieStore.set(OIDC_ID_TOKEN_COOKIE, tokens.id_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: TOKEN_MAX_AGE_SEC,
    path: "/",
  });

  if (tokens.refresh_token) {
    cookieStore.set(OIDC_REFRESH_TOKEN_COOKIE, tokens.refresh_token, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      maxAge: TOKEN_MAX_AGE_SEC * 7, // 7 days for refresh token
      path: "/",
    });
  }

  // Store session info for quick access
  cookieStore.set(OIDC_SESSION_COOKIE, JSON.stringify(sessionUser), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: TOKEN_MAX_AGE_SEC,
    path: "/",
  });

  return sessionUser;
}

// ── Session reading ─────────────────────────────────────────────────

export async function getOidcSession(): Promise<SessionUser | null> {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get(OIDC_SESSION_COOKIE)?.value;
  if (!sessionCookie) return null;

  try {
    const parsed = JSON.parse(sessionCookie);
    if (!parsed.learner_id || !parsed.role) return null;
    return {
      learner_id: parsed.learner_id,
      org_id: parsed.org_id ?? null,
      role: parsed.role,
      name: parsed.name || parsed.learner_id,
    };
  } catch {
    return null;
  }
}

export async function clearOidcSession(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(OIDC_ID_TOKEN_COOKIE);
  cookieStore.delete(OIDC_REFRESH_TOKEN_COOKIE);
  cookieStore.delete(OIDC_SESSION_COOKIE);
}

import { createHmac, timingSafeEqual } from "node:crypto";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import type { SessionUser, MockUser } from "@/lib/mock-users";
import { MOCK_USERS } from "@/lib/mock-users";
import { getOidcSession } from "@/lib/oidc";

// ── Auth mode ──────────────────────────────────────────────────────────

export type { SessionUser, MockUser } from "@/lib/mock-users";
export { MOCK_USERS } from "@/lib/mock-users";

export type DeployEnv = "development" | "staging" | "production";

export function getAuthMode(): "disabled" | "mock" | "oidc" {
  const raw = (process.env.AUTH_MODE || "disabled").trim().toLowerCase();
  if (raw === "mock") return "mock";
  if (raw === "oidc") return "oidc";
  return "disabled";
}

const MOCK_USER_MAP = new Map(MOCK_USERS.map((u) => [u.id, u]));

// ── Role helpers ──────────────────────────────────────────────────────

export const LEARNER_DATA_ROLES = [
  "supervisor",
  "organization_admin",
  "platform_admin",
] as const;

export const TEAM_VIEW_ROLES = [
  "supervisor",
  "organization_admin",
  "platform_admin",
] as const;

export const ORGANIZATION_REPORT_ROLES = TEAM_VIEW_ROLES;

export const ADMIN_OPERATION_ROLES = [
  "organization_admin",
  "content_admin",
  "platform_admin",
] as const;

function normalizeRole(role: string | null | undefined): string {
  return typeof role === "string" ? role.trim().toLowerCase() : "";
}

function roleIn(user: SessionUser, roles: readonly string[]): boolean {
  return roles.includes(normalizeRole(user.role));
}

export function canAccessLearner(user: SessionUser, learnerId: string): boolean {
  const normalizedLearnerId = learnerId.trim();
  if (!normalizedLearnerId) return false;
  return user.learner_id === normalizedLearnerId || roleIn(user, LEARNER_DATA_ROLES);
}

export function canViewTeam(user: SessionUser): boolean {
  return roleIn(user, TEAM_VIEW_ROLES);
}

export function canViewOrganizationReports(user: SessionUser): boolean {
  return roleIn(user, ORGANIZATION_REPORT_ROLES);
}

export function canViewAdminOperations(user: SessionUser): boolean {
  return roleIn(user, ADMIN_OPERATION_ROLES);
}

// ── Session cookie helpers ─────────────────────────────────────────────

const SESSION_COOKIE_NAME = "session";
const SESSION_MAX_AGE_SEC = 86400; // 24 hours

function getSessionSecret(): string {
  return process.env.SESSION_SECRET || "dev-secret-not-for-production";
}

function encodeBase64Url(data: string): string {
  return Buffer.from(data)
    .toString("base64url")
    .replace(/=+$/, "");
}

function decodeBase64Url(data: string): string {
  return Buffer.from(data, "base64url").toString("utf-8");
}

function signPayload(payload: string, secret: string): string {
  return createHmac("sha256", secret).update(payload).digest("hex");
}

function signaturesMatch(value: string, expected: string): boolean {
  const valueBuffer = Buffer.from(value);
  const expectedBuffer = Buffer.from(expected);
  return (
    valueBuffer.length === expectedBuffer.length &&
    timingSafeEqual(valueBuffer, expectedBuffer)
  );
}

function serializeSessionCookie(user: SessionUser): string {
  const nowSec = Math.floor(Date.now() / 1000);
  const payload = JSON.stringify({
    learner_id: user.learner_id,
    org_id: user.org_id ?? null,
    role: user.role,
    name: user.name,
    exp: nowSec + SESSION_MAX_AGE_SEC,
  });
  const encoded = encodeBase64Url(payload);
  const sig = signPayload(encoded, getSessionSecret());
  return `${encoded}.${sig}`;
}

function parseSessionCookie(
  value: string | undefined,
): SessionUser | null {
  if (!value) return null;
  const dot = value.indexOf(".");
  if (dot === -1) return null;
  const encoded = value.slice(0, dot);
  const sig = value.slice(dot + 1);
  const secret = getSessionSecret();
  const expectedSig = signPayload(encoded, secret);
  if (!signaturesMatch(sig, expectedSig)) return null;
  try {
    const parsed = JSON.parse(decodeBase64Url(encoded));
    if (!parsed.learner_id || !parsed.role) return null;
    if (typeof parsed.exp !== "number" || parsed.exp < Math.floor(Date.now() / 1000)) {
      return null;
    }
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

// ── Server-side session API ────────────────────────────────────────────

export async function getServerSession(): Promise<SessionUser | null> {
  const authMode = getAuthMode();
  if (authMode === "disabled") return null;
  if (authMode === "oidc") return getOidcSession();
  const cookieStore = await cookies();
  return parseSessionCookie(cookieStore.get(SESSION_COOKIE_NAME)?.value);
}

export async function requireServerSession(): Promise<SessionUser> {
  const session = await getServerSession();
  if (!session) {
    redirect("/login");
  }
  return session;
}

export async function requireMockSession(): Promise<SessionUser | null> {
  if (getAuthMode() !== "mock") return null;
  return requireServerSession();
}

export async function requireMockRole(
  roles: readonly string[],
  redirectTo = "/",
): Promise<SessionUser | null> {
  const session = await requireMockSession();
  if (session && !roleIn(session, roles)) {
    redirect(redirectTo);
  }
  return session;
}

export async function createSession(user: SessionUser): Promise<void> {
  const cookieStore = await cookies();
  const value = serializeSessionCookie(user);
  cookieStore.set(SESSION_COOKIE_NAME, value, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: SESSION_MAX_AGE_SEC,
    path: "/",
  });
}

export async function clearSession(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(SESSION_COOKIE_NAME);
  // Also clear OIDC cookies if present
  cookieStore.delete("oidc_id_token");
  cookieStore.delete("oidc_refresh_token");
  cookieStore.delete("oidc_session");
}

// ── Password auth ──────────────────────────────────────────────────────

export const DEFAULT_PASSWORD = "Welcome123";

export function verifyPassword(input: string): boolean {
  return input === DEFAULT_PASSWORD;
}

// ── Mock user lookup ───────────────────────────────────────────────────

export function findMockUser(id: string): MockUser | undefined {
  return MOCK_USER_MAP.get(id);
}

export function authenticateMockUser(id: string): SessionUser | null {
  const user = findMockUser(id);
  if (!user) return null;
  return {
    learner_id: user.learner_id,
    org_id: user.org_id,
    role: user.role,
    name: user.name,
  };
}

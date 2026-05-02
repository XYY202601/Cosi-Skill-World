export type StartSessionErrorKind =
  | "skill_not_installed"
  | "permission"
  | "unknown";

export type StartSessionErrorDetails = {
  kind: StartSessionErrorKind;
  message: string;
  skillId?: string;
  orgId?: string;
};

const SKILL_NOT_INSTALLED_PATTERN =
  /Skill\s+[`'"]?([\w-]+)[`'"]?\s+is\s+not\s+installed\s+for\s+organization\s+[`'"]?([\w.-]+)[`'"]?/i;

const PERMISSION_ERROR_PATTERN =
  /403|forbidden|restricted|denied|raw session transcripts/i;

export function startSessionErrorMessage(
  error: unknown,
  fallback = "Unknown scenario start error"
): string {
  if (error instanceof Error) {
    const message = error.message.trim();
    if (message) {
      return message;
    }
  }
  if (typeof error === "string" && error.trim()) {
    return error.trim();
  }
  return fallback;
}

export function isPermissionErrorMessage(message: string): boolean {
  return PERMISSION_ERROR_PATTERN.test(message);
}

export function parseStartSessionError(
  error: unknown,
  fallback = "Unknown scenario start error"
): StartSessionErrorDetails {
  const message = startSessionErrorMessage(error, fallback);
  const skillMatch = message.match(SKILL_NOT_INSTALLED_PATTERN);
  if (skillMatch) {
    return {
      kind: "skill_not_installed",
      message,
      skillId: skillMatch[1],
      orgId: skillMatch[2],
    };
  }

  if (isPermissionErrorMessage(message)) {
    return {
      kind: "permission",
      message,
    };
  }

  return {
    kind: "unknown",
    message,
  };
}

export function canManageSkillInstall(role: string | null | undefined): boolean {
  return role === "organization_admin" || role === "platform_admin";
}

import { LEARNER_DATA_ROLES, canAccessLearner, requireMockSession } from "@/lib/auth";
import { ProgressFlow } from "@/features/sessions/progress-flow";

export const dynamic = "force-dynamic";

type ProgressPageProps = {
  searchParams: Promise<{ learner?: string; org?: string; viewer?: string }>;
};

export default async function ProgressPage({ searchParams }: ProgressPageProps) {
  const resolvedSearchParams = await searchParams;

  const requestedLearnerId = resolvedSearchParams.learner?.trim() || null;
  let initialLearnerId = requestedLearnerId ?? "learner_demo_001";
  let orgId: string | null = resolvedSearchParams.org ?? null;
  let viewerRole: string | null = resolvedSearchParams.viewer ?? null;

  const session = await requireMockSession();
  if (session) {
    const canBrowseLearnerData = LEARNER_DATA_ROLES.includes(
      session.role as (typeof LEARNER_DATA_ROLES)[number],
    );
    initialLearnerId = session.learner_id;
    if (requestedLearnerId && canAccessLearner(session, requestedLearnerId)) {
      initialLearnerId = requestedLearnerId;
    }
    if (orgId == null) {
      orgId = canBrowseLearnerData ? "global" : session.org_id ?? null;
    }
    viewerRole = session.role;
  }

  return (
    <ProgressFlow
      initialLearnerId={initialLearnerId}
      orgId={orgId}
      viewerRole={viewerRole}
    />
  );
}

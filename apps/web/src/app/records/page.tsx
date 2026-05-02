import { LEARNER_DATA_ROLES, canAccessLearner, requireMockSession } from "@/lib/auth";
import { RecordsFlow } from "@/features/sessions/records-flow";

export const dynamic = "force-dynamic";

const DEFAULT_LEARNER_ID = "learner_demo_001";

type RecordsPageProps = {
  searchParams: Promise<{
    compliance_severity?: string;
    difficulty?: string;
    finish_reason?: string;
    learner?: string;
    org?: string;
    page?: string;
    persona?: string;
    prompt_profile?: string;
    q?: string;
    score_band?: string;
    scenario?: string;
    sort?: string;
    weak_skill?: string;
  }>;
};

export default async function RecordsPage({ searchParams }: RecordsPageProps) {
  const resolvedSearchParams = await searchParams;

  const requestedLearnerId = resolvedSearchParams.learner?.trim() || null;
  let learnerId = requestedLearnerId ?? DEFAULT_LEARNER_ID;
  let orgId: string | null = resolvedSearchParams.org ?? null;
  let viewerRole: string | null = null;
  const session = await requireMockSession();
  if (session) {
    const canBrowseLearnerData = LEARNER_DATA_ROLES.includes(
      session.role as (typeof LEARNER_DATA_ROLES)[number],
    );
    viewerRole = session.role;
    learnerId = session.learner_id;
    if (requestedLearnerId && canAccessLearner(session, requestedLearnerId)) {
      learnerId = requestedLearnerId;
    }
    if (orgId == null) {
      orgId = canBrowseLearnerData ? "global" : session.org_id ?? null;
    }
  }

  return (
    <RecordsFlow
      initialLearnerId={learnerId}
      initialSearchParams={resolvedSearchParams}
      orgId={orgId}
      viewerRole={viewerRole}
    />
  );
}

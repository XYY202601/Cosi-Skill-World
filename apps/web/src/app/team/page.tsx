import { TEAM_VIEW_ROLES, requireMockRole } from "@/lib/auth";
import { TeamFlow } from "@/features/supervisor/team-flow";
import { TrainingPlansTracker } from "@/features/supervisor/training-plans-tracker";

export const dynamic = "force-dynamic";

type TeamPageProps = {
  searchParams: Promise<{ org?: string; viewer?: string }>;
};

export default async function TeamPage({ searchParams }: TeamPageProps) {
  const resolvedSearchParams = await searchParams;

  let initialOrganizationId = resolvedSearchParams.org ?? "global";
  let viewerRole = resolvedSearchParams.viewer ?? "supervisor";

  const session = await requireMockRole(TEAM_VIEW_ROLES);
  if (session) {
    initialOrganizationId = resolvedSearchParams.org ?? session.org_id ?? "global";
    if (!resolvedSearchParams.org && initialOrganizationId.toLowerCase() === "local") {
      initialOrganizationId = "global";
    }
    viewerRole = session.role;
  }

  return (
    <>
      <TeamFlow
        initialOrganizationId={initialOrganizationId}
        viewerRole={viewerRole}
      />
      <TrainingPlansTracker
        organizationId={initialOrganizationId}
        viewerRole={viewerRole}
      />
    </>
  );
}

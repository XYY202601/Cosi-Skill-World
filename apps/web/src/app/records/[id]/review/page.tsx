import { requireMockSession } from "@/lib/auth";
import { ReviewFlow } from "@/features/sessions/review-flow";

export const dynamic = "force-dynamic";

type RecordReviewPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ org?: string; viewer?: string }>;
};

export default async function RecordReviewPage({
  params,
  searchParams,
}: RecordReviewPageProps) {
  const resolvedParams = await params;
  const resolvedSearchParams = await searchParams;

  let orgId: string | null = resolvedSearchParams.org ?? null;
  let viewerRole: string | null = resolvedSearchParams.viewer ?? null;

  const session = await requireMockSession();
  if (session) {
    orgId = session.org_id ?? null;
    viewerRole = session.role;
  }

  return (
    <ReviewFlow
      sessionId={resolvedParams.id}
      orgId={orgId}
      viewerRole={viewerRole}
    />
  );
}

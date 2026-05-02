import { requireMockSession } from "@/lib/auth";
import { SessionFlow } from "@/features/sessions/session-flow";

export const dynamic = "force-dynamic";

type SessionPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ scenario?: string }>;
};

export default async function SessionPage({ params, searchParams }: SessionPageProps) {
  const resolvedParams = await params;
  const resolvedSearchParams = await searchParams;
  await requireMockSession();

  return (
    <SessionFlow
      sessionId={resolvedParams.id}
      scenarioId={resolvedSearchParams.scenario ?? null}
    />
  );
}

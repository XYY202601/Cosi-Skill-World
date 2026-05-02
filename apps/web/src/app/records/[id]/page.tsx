import { requireMockSession } from "@/lib/auth";
import { SessionFlow } from "@/features/sessions/session-flow";

export const dynamic = "force-dynamic";

type RecordSessionPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{
    finish_reason?: string;
    highlight_turn?: string;
    scenario?: string;
    scenario_filter?: string;
    weak_skill?: string;
  }>;
};

export default async function RecordSessionPage({ params, searchParams }: RecordSessionPageProps) {
  const resolvedParams = await params;
  const resolvedSearchParams = await searchParams;
  await requireMockSession();
  const parsedHighlightTurn = resolvedSearchParams.highlight_turn
    ? Number.parseInt(resolvedSearchParams.highlight_turn, 10)
    : null;

  return (
    <SessionFlow
      historicalSelection={{
        finishReason: resolvedSearchParams.finish_reason ?? null,
        highlightTurn:
          typeof parsedHighlightTurn === "number" && Number.isFinite(parsedHighlightTurn)
            ? parsedHighlightTurn
            : null,
        scenarioFilter: resolvedSearchParams.scenario_filter ?? null,
        weakSkill: resolvedSearchParams.weak_skill ?? null,
      }}
      sessionId={resolvedParams.id}
      scenarioId={resolvedSearchParams.scenario ?? null}
    />
  );
}

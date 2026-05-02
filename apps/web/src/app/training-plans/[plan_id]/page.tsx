import { TEAM_VIEW_ROLES, requireMockRole } from "@/lib/auth";
import { PlanDetail } from "@/features/training-plans/plan-detail";

export const dynamic = "force-dynamic";

type PlanDetailPageProps = {
  params: Promise<{ plan_id: string }>;
};

export default async function PlanDetailPage({ params }: PlanDetailPageProps) {
  const { plan_id } = await params;
  await requireMockRole(TEAM_VIEW_ROLES);
  return <PlanDetail planId={plan_id} />;
}

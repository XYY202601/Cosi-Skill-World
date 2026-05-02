import { requireMockSession } from "@/lib/auth";
import { ScenariosFlow } from "@/features/scenarios/scenarios-flow";

export const dynamic = "force-dynamic";

export default async function ScenariosPage() {
  await requireMockSession();
  return <ScenariosFlow />;
}

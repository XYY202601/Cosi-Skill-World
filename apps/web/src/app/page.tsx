import { requireMockSession } from "@/lib/auth";
import { HomeDashboard } from "@/features/home/home-dashboard";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  await requireMockSession();
  return <HomeDashboard />;
}

import { requireMockSession } from "@/lib/auth";
import { MarketplaceFlow } from "@/features/marketplace/marketplace-flow";

export const dynamic = "force-dynamic";

export default async function MarketplacePage() {
  await requireMockSession();
  return <MarketplaceFlow />;
}

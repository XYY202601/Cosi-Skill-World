import { redirect } from "next/navigation";

import { requireMockSession } from "@/lib/auth";

export const dynamic = "force-dynamic";

type ReviewPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ org?: string; viewer?: string }>;
};

export default async function ReviewPage({ params, searchParams }: ReviewPageProps) {
  const resolvedParams = await params;
  const resolvedSearchParams = await searchParams;
  await requireMockSession();
  const redirectTarget = new URL(
    `/records/${resolvedParams.id}/review`,
    "http://runtime-proxy.local"
  );
  if (resolvedSearchParams.org) {
    redirectTarget.searchParams.set("org", resolvedSearchParams.org);
  }
  if (resolvedSearchParams.viewer) {
    redirectTarget.searchParams.set("viewer", resolvedSearchParams.viewer);
  }
  redirect(`${redirectTarget.pathname}${redirectTarget.search}`);
}

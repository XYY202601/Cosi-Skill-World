import { ADMIN_OPERATION_ROLES, requireMockRole } from "@/lib/auth";
import { AdminFlow } from "@/features/admin/admin-flow";
import { TrainingPlansFlow } from "@/features/admin/training-plans-flow";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  await requireMockRole(ADMIN_OPERATION_ROLES);
  return (
    <div className="admin-page-layout">
      <AdminFlow />
      <hr className="admin-section-divider" />
      <TrainingPlansFlow />
    </div>
  );
}

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalSection from "@/components/PortalSection";
import PortalShell from "@/components/PortalShell";
import WorkflowPanel from "@/components/WorkflowPanel";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import type { PortalPayload, User } from "@/lib/types";

const COLUMNS = [["id", "Payment reference"], ["student", "Student"], ["division", "Division"], ["type", "Fee type"], ["amount", "Amount"], ["currency", "Currency"], ["status", "Status"]].map(([key, label]) => ({ key, label }));
const NO_VIEW = "You don't have permission to view payments. A Super Admin can grant Payments: View in Permissions.";
const UNAVAILABLE = "Payments are unavailable right now. Please try again.";

// nehn-021 (DEC-SCOPE-309 D4/D6): the finance roles' payments, both divisions, and the Apply discount form. Both are grant-driven:
// GET /admin/payments needs `payments.view` (else the refusal replaces the table) and the form needs `discounts.add` (WorkflowPanel).
export default async function ManagementPaymentsPage() {
  let me: ManagementMe;
  let user: User;
  try {
    [me, user] = await Promise.all([serverApi<ManagementMe>("/api/v1/management/me"), serverApi<User>("/api/v1/auth/me")]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let rows: Record<string, unknown>[] = [];
  let error = "";
  try {
    rows = await serverApi<Record<string, unknown>[]>("/api/v1/admin/payments");
  } catch (e) {
    error = e instanceof ApiError && e.status === 403 ? NO_VIEW : UNAVAILABLE;
  }
  const data: PortalPayload = {
    title: "Payments",
    subtitle: "Fees across IT and Overseas. A discount lowers a still-unpaid fee and needs a written reason; every discount is audited.",
    metrics: [], actions: [], columns: COLUMNS, rows,
    panels: error ? [{ title: "Payments unavailable", items: [error] }] : [],
  };
  return (
    <PortalShell nav={managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <PortalSection data={data} table={!error} emptyText="No payments yet" />
      <WorkflowPanel user={user} section="payments" />
    </PortalShell>
  );
}

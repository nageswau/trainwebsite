import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementExpenses from "@/components/ManagementExpenses";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { expenseMonth, expensesUrl, istMonth, type ExpenseDashboard } from "@/lib/managementExpenses";

const UNAVAILABLE = "The expense dashboard is unavailable right now. Please try again.";

// mgmt-010 (EVID-017 §8, spec ME1-ME10): the expense dashboard for the finance tier. The API refuses everyone else (the super admin
// included, M13), and that refusal is shown as the access card. A future month typed into the address gets the API's 422 message.
export default async function ManagementExpensesPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const month = expenseMonth(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: ExpenseDashboard | null = null;
  let error = "";
  try {
    data = await serverApi<ExpenseDashboard>(expensesUrl(month));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = e instanceof ApiError && e.status === 422 ? e.message : UNAVAILABLE;
  }
  return (
    <PortalShell nav={managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">
              <Link href={MANAGEMENT_HOME}>Command Center</Link>
            </div>
            <h2>Expense dashboard</h2>
          </div>
        </div>
        <ManagementExpenses data={data} error={error} month={month} maxMonth={istMonth()} />
      </div>
    </PortalShell>
  );
}

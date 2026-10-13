import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementAbroadRevenue from "@/components/ManagementAbroadRevenue";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { abroadRevenueUrl, type AbroadRevenue } from "@/lib/managementAbroadRevenue";
import { expenseMonth, istMonth } from "@/lib/managementExpenses";

const UNAVAILABLE = "The Abroad revenue dashboard is unavailable right now. Please try again.";

// mgmt-006 (EVID-017 §4, spec MR1-MR12): the Abroad Education revenue dashboard for the finance tier. The API refuses everyone else (the
// super admin included, M13), and that refusal is shown as the access card. A future month typed into the address gets the API's 422.
export default async function ManagementAbroadRevenuePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const month = expenseMonth(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: AbroadRevenue | null = null;
  let error = "";
  try {
    data = await serverApi<AbroadRevenue>(abroadRevenueUrl(month));
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
            <h2>Abroad Education revenue</h2>
          </div>
        </div>
        <ManagementAbroadRevenue data={data} error={error} month={month} maxMonth={istMonth()} />
      </div>
    </PortalShell>
  );
}

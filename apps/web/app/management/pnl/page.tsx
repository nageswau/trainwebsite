import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementPnl from "@/components/ManagementPnl";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { istMonth } from "@/lib/managementExpenses";
import { pnlQuery, pnlUrl, type Pnl } from "@/lib/managementPnl";

const UNAVAILABLE = "Profit & loss is unavailable right now. Please try again.";

// mgmt-009 (EVID-017 §7, spec PL1-PL12): the company P&L for the finance tier. The API refuses everyone else (the super admin
// included, M13), shown as the access card; a 422 (a month out of range) keeps the form so another month can be chosen.
export default async function ManagementPnlPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = pnlQuery(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: Pnl | null = null;
  let error = "";
  try {
    data = await serverApi<Pnl>(pnlUrl(query));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = e instanceof ApiError && e.status === 422 && typeof e.message === "string" && !e.message.startsWith("[object") ? e.message : UNAVAILABLE;
  }
  return (
    <PortalShell nav={managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">
              <Link href={MANAGEMENT_HOME}>Command Center</Link>
            </div>
            <h2>Profit &amp; loss</h2>
          </div>
        </div>
        <ManagementPnl data={data} error={error} query={query} maxMonth={istMonth()} />
      </div>
    </PortalShell>
  );
}

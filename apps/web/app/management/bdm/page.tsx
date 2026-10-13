import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementBdm from "@/components/ManagementBdm";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { bdmDashboardQuery, bdmDashboardUrl, type BdmDashboard } from "@/lib/managementBdm";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const UNAVAILABLE = "BDM figures are unavailable right now. Please try again.";

// mgmt-020 (EVID-017 §16, spec BD1-BD12): the operational tier (partner, super_admin) reads one BDM type's figures per tab. The super
// admin keeps their own sidebar (MG10); anyone else is refused by the API, shown as the access card.
export default async function ManagementBdmPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = bdmDashboardQuery(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: BdmDashboard | null = null;
  let error = "";
  try {
    data = await serverApi<BdmDashboard>(bdmDashboardUrl(query));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = e instanceof ApiError && e.status === 422 && typeof e.message === "string" && !e.message.startsWith("[object") ? e.message : UNAVAILABLE;
  }
  return (
    <PortalShell nav={me.role === "super_admin" ? SUPER_ADMIN_NAV : managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">
              <Link href={MANAGEMENT_HOME}>Command Center</Link>
            </div>
            <h2>BDM dashboards</h2>
          </div>
        </div>
        <ManagementBdm data={data} error={error} query={query} />
      </div>
    </PortalShell>
  );
}

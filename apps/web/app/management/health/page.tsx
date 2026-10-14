import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementHealth from "@/components/ManagementHealth";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { istMonth } from "@/lib/managementExpenses";
import { healthQuery, healthUrl, type BusinessHealth } from "@/lib/managementHealth";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const UNAVAILABLE = "Business health is unavailable right now. Please try again.";

// mgmt-030 (EVID-017 §30, spec BH1-BH14): the operational tier (partner, super_admin) reads the business health score. The super admin
// keeps their own sidebar and gets the operational factors only (M13); anyone else is refused by the API, shown as the access card.
export default async function ManagementHealthPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = healthQuery(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: BusinessHealth | null = null;
  let error = "";
  try {
    data = await serverApi<BusinessHealth>(healthUrl(query));
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
            <h2>Business health score</h2>
          </div>
        </div>
        <ManagementHealth data={data} error={error} query={query} maxMonth={istMonth()} />
      </div>
    </PortalShell>
  );
}

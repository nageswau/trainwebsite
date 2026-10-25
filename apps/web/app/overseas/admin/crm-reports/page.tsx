import { redirect } from "next/navigation";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import ManagementCrmReports from "@/components/ManagementCrmReports";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { ADMIN_CRM_REPORTS_HOME, CRM_REPORTS_UNAVAILABLE, crmFilters, crmReportsHref, crmReportsUrl, type CrmReports } from "@/lib/managementCrmReports";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ccrm-034 (DEC-SCOPE-263, R1): the same CRM reports for the Overseas Admin (CC3: the team-wide view). Super Admin passes too.
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function AdminCrmReportsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const search = await searchParams;
  const filters = crmFilters(search);
  if (Object.values(search).some((value) => value === "")) redirect(crmReportsHref(ADMIN_CRM_REPORTS_HOME, filters));
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e);
  }
  if (!ADMIN_ROLES.includes(user.role)) return accessDenied(user, "Overseas Administrator role required");
  let data: CrmReports | null = null;
  let error = "";
  try {
    data = await serverApi<CrmReports>(crmReportsUrl(filters));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e);
    error = e instanceof ApiError && e.status === 422 ? e.message : CRM_REPORTS_UNAVAILABLE;
  }
  return (
    <PortalShell nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>CRM reports</h2>
            <p className="muted">Application ageing, university and visa outcomes, document readiness, and lead conversion and forecast by intake.</p>
          </div>
        </div>
        <ManagementCrmReports data={data} error={error} filters={filters} home={ADMIN_CRM_REPORTS_HOME} />
      </div>
    </PortalShell>
  );
}

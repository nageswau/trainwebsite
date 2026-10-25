import Link from "next/link";
import { redirect } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementCrmReports from "@/components/ManagementCrmReports";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { CRM_REPORTS_HOME, CRM_REPORTS_UNAVAILABLE, crmFilters, crmReportsHref, crmReportsUrl, type CrmReports } from "@/lib/managementCrmReports";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// ccrm-034 (DEC-SCOPE-263, R1): the management CRM reports in the Command Center (partner, super_admin). The API refuses everyone else,
// and that refusal is shown as the access card. A 422 (the date order) shows the API's words.
export default async function ManagementCrmReportsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const search = await searchParams;
  const filters = crmFilters(search);
  // The GET form sends every field; one redirect drops the empty ones so the address is short and shareable (QA24-01).
  if (Object.values(search).some((value) => value === "")) redirect(crmReportsHref(CRM_REPORTS_HOME, filters));
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: CrmReports | null = null;
  let error = "";
  try {
    data = await serverApi<CrmReports>(crmReportsUrl(filters));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = e instanceof ApiError && e.status === 422 ? e.message : CRM_REPORTS_UNAVAILABLE;
  }
  return (
    <PortalShell nav={me.role === "super_admin" ? SUPER_ADMIN_NAV : managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">
              <Link href={MANAGEMENT_HOME}>Command Center</Link>
            </div>
            <h2>CRM reports</h2>
          </div>
        </div>
        <ManagementCrmReports data={data} error={error} filters={filters} home={CRM_REPORTS_HOME} />
      </div>
    </PortalShell>
  );
}

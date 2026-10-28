import { accessUnavailable } from "@/components/AccessUnavailable";
import CrmUniversityApplications, { crmUniversityError } from "@/components/CrmUniversityApplications";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import {
  CRM_REPORTS_HOME, CRM_UNIVERSITY_NOT_FOUND, crmFilters, crmPage, crmUniversityApplicationsUrl, isUuid, type CrmUniversityApplications as Data,
} from "@/lib/managementCrmReports"; // prettier-ignore
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// ccrm-052: the Command Center's drill-down from a University performance row (partner, super_admin). The API refuses everyone else.
export default async function ManagementCrmUniversityPage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ id }, search] = await Promise.all([params, searchParams]);
  const filters = crmFilters(search);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: Data | null = null;
  let error = CRM_UNIVERSITY_NOT_FOUND;
  if (isUuid(id)) {
    try {
      data = await serverApi<Data>(crmUniversityApplicationsUrl(id, filters, crmPage(search)));
      error = "";
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
      error = crmUniversityError(e);
    }
  }
  return (
    <PortalShell nav={me.role === "super_admin" ? SUPER_ADMIN_NAV : managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <CrmUniversityApplications data={data} error={error} filters={filters} home={CRM_REPORTS_HOME} />
      </div>
    </PortalShell>
  );
}

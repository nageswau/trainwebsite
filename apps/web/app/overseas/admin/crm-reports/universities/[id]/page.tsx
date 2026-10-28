import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import CrmUniversityApplications, { crmUniversityError } from "@/components/CrmUniversityApplications";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import {
  ADMIN_CRM_REPORTS_HOME, CRM_UNIVERSITY_NOT_FOUND, crmFilters, crmPage, crmUniversityApplicationsUrl, isUuid, type CrmUniversityApplications as Data,
} from "@/lib/managementCrmReports"; // prettier-ignore
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ccrm-052: the Overseas Admin's drill-down from a University performance row (Super Admin passes too, as on the report).
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function AdminCrmUniversityPage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ id }, search] = await Promise.all([params, searchParams]);
  const filters = crmFilters(search);
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e);
  }
  if (!ADMIN_ROLES.includes(user.role)) return accessDenied(user, "Overseas Administrator role required");
  let data: Data | null = null;
  let error = CRM_UNIVERSITY_NOT_FOUND;
  if (isUuid(id)) {
    try {
      data = await serverApi<Data>(crmUniversityApplicationsUrl(id, filters, crmPage(search)));
      error = "";
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e);
      error = crmUniversityError(e);
    }
  }
  return (
    <PortalShell nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" userName={user.full_name}>
      <div className="portal-content">
        <CrmUniversityApplications data={data} error={error} filters={filters} home={ADMIN_CRM_REPORTS_HOME} />
      </div>
    </PortalShell>
  );
}

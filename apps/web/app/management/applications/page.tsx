import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementApplications from "@/components/ManagementApplications";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { applicationsUrl, funnelFilters, type ApplicationFunnel } from "@/lib/managementApplications";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const UNAVAILABLE = "The applications funnel is unavailable right now. Please try again.";

// mgmt-024 (EVID-017 §20, spec MF18): the application funnel for the operational tier (partner, super_admin). The API refuses everyone
// else (the accountant's 403 included), and that refusal is shown as the access card. A 422 (the date order) shows the API's words.
export default async function ManagementApplicationsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const filters = funnelFilters(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: ApplicationFunnel | null = null;
  let error = "";
  try {
    data = await serverApi<ApplicationFunnel>(applicationsUrl(filters));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    error = e instanceof ApiError && e.status === 422 ? e.message : UNAVAILABLE;
  }
  return (
    <PortalShell nav={me.role === "super_admin" ? SUPER_ADMIN_NAV : managementNavFor(me.tiers)} roleLabel={MANAGEMENT_ROLE_LABEL[me.role] ?? me.role} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">
              <Link href={MANAGEMENT_HOME}>Command Center</Link>
            </div>
            <h2>Applications funnel</h2>
          </div>
        </div>
        <ManagementApplications data={data} error={error} filters={filters} />
      </div>
    </PortalShell>
  );
}

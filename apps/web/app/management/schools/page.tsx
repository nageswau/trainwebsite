import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementSchools from "@/components/ManagementSchools";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { schoolsQuery, schoolsUrl, type SchoolsDashboard } from "@/lib/managementSchools";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const UNAVAILABLE = "School figures are unavailable right now. Please try again.";

// mgmt-022 (EVID-017 §18, spec SD1-SD16): every management role reads the school dashboard for a period; only the finance tier (partners
// and the accountant) gets money and edits the values (SD1, SD13). The super admin keeps their own sidebar (MG10); anyone else is refused
// by the API, shown as the access card.
export default async function ManagementSchoolsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = schoolsQuery(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: SchoolsDashboard | null = null;
  let error = "";
  try {
    data = await serverApi<SchoolsDashboard>(schoolsUrl(query));
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
            <h2>School dashboard</h2>
          </div>
        </div>
        <ManagementSchools data={data} error={error} query={query} />
      </div>
    </PortalShell>
  );
}

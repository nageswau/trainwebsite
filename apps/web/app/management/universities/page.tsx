import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementUniversities from "@/components/ManagementUniversities";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { universitiesQuery, universitiesUrl, type UniversitiesDashboard } from "@/lib/managementUniversities";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const UNAVAILABLE = "University partnership figures are unavailable right now. Please try again.";

// mgmt-023 (EVID-017 §19, spec UD1-UD14): the operational tier (partner, super_admin) reads the university partnerships. The super admin
// keeps their own sidebar and gets no revenue (M13); anyone else is refused by the API, shown as the access card.
export default async function ManagementUniversitiesPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = universitiesQuery(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: UniversitiesDashboard | null = null;
  let error = "";
  try {
    data = await serverApi<UniversitiesDashboard>(universitiesUrl(query));
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
            <h2>University partnership dashboard</h2>
          </div>
        </div>
        <ManagementUniversities data={data} error={error} query={query} />
      </div>
    </PortalShell>
  );
}

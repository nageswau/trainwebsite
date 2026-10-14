import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementFunnel from "@/components/ManagementFunnel";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { funnelQuery, funnelUrl, type StudentFunnel } from "@/lib/managementFunnel";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const UNAVAILABLE = "Student funnel figures are unavailable right now. Please try again.";

// mgmt-016 (EVID-017 §11, spec SF1-SF16): the operational tier (partner, super_admin) reads the student funnel for a period, optionally
// broken down by one dimension. The super admin keeps their own sidebar (MG10); anyone else is refused by the API, shown as the access card.
export default async function ManagementFunnelPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = funnelQuery(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: StudentFunnel | null = null;
  let error = "";
  try {
    data = await serverApi<StudentFunnel>(funnelUrl(query));
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
            <h2>Student funnel</h2>
          </div>
        </div>
        <ManagementFunnel data={data} error={error} query={query} />
      </div>
    </PortalShell>
  );
}

import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementCounseling from "@/components/ManagementCounseling";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { counselingQuery, counselingUrl, type CounselingDashboard } from "@/lib/managementCounseling";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const UNAVAILABLE = "Counseling figures are unavailable right now. Please try again.";

// mgmt-018 (EVID-017 §13, spec CS1-CS12): the operational tier (partner, super_admin) reads every counselor's figures for a period. The
// super admin keeps their own sidebar (MG10) and gets no revenue (CS8); anyone else is refused by the API, shown as the access card.
export default async function ManagementCounselingPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = counselingQuery(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: CounselingDashboard | null = null;
  let error = "";
  try {
    data = await serverApi<CounselingDashboard>(counselingUrl(query));
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
            <h2>Counseling dashboard</h2>
          </div>
        </div>
        <ManagementCounseling data={data} error={error} query={query} />
      </div>
    </PortalShell>
  );
}

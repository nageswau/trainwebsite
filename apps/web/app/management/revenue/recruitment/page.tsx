import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementRecruitmentRevenue from "@/components/ManagementRecruitmentRevenue";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { istMonth } from "@/lib/managementExpenses";
import { recruitmentRevenueQuery, recruitmentRevenueUrl, type RecruitmentRevenue } from "@/lib/managementRecruitmentRevenue";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const UNAVAILABLE = "Recruitment figures are unavailable right now. Please try again.";

// mgmt-008 (EVID-017 §6, spec RR1-RR12): every management role reads the KPIs; the finance tier also gets revenue (RR9). The super admin
// keeps their own sidebar (MG10) and sees the KPI page; anyone else is refused by the API, shown as the access card.
export default async function ManagementRecruitmentRevenuePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = recruitmentRevenueQuery(await searchParams);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: RecruitmentRevenue | null = null;
  let error = "";
  try {
    data = await serverApi<RecruitmentRevenue>(recruitmentRevenueUrl(query));
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
            <h2>{me.tiers.finance ? "Recruitment & Placement revenue" : "Recruitment & Placement KPIs"}</h2>
          </div>
        </div>
        <ManagementRecruitmentRevenue data={data} error={error} query={query} maxMonth={istMonth()} />
      </div>
    </PortalShell>
  );
}

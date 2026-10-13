import Link from "next/link";
import { redirect } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import ManagementRecruitment from "@/components/ManagementRecruitment";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_HOME, MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { recruitmentFilters, recruitmentHref, recruitmentUrl, type Recruitment } from "@/lib/managementRecruitment";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

const UNAVAILABLE = "The recruitment dashboard is unavailable right now. Please try again.";

// mgmt-025 (EVID-017 §21, spec RC10): the company-wide Recruitment dashboard for the operational tier (partner, super_admin); revenue only
// for the partner. The API refuses everyone else (the accountant's 403 included), shown as the access card. A 422 shows the API's words.
export default async function ManagementRecruitmentPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const search = await searchParams;
  const filters = recruitmentFilters(search);
  // The GET form sends both dates; one redirect drops an empty one so the address is short and shareable.
  if (Object.values(search).some((value) => value === "")) redirect(recruitmentHref(filters));
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let data: Recruitment | null = null;
  let error = "";
  try {
    data = await serverApi<Recruitment>(recruitmentUrl(filters));
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
            <h2>Recruitment</h2>
          </div>
        </div>
        <ManagementRecruitment data={data} error={error} filters={filters} />
      </div>
    </PortalShell>
  );
}

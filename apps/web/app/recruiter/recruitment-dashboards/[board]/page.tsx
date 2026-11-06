import { notFound, redirect } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruitmentDashboard from "@/components/RecruitmentDashboard";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { PORTAL_NAV, type NavItem } from "@/lib/navigation";
import { companyShell } from "@/lib/recruiterCompanies";
import { boardUrl, dashboardError, dashboardQuery, drillUrl, isBoard, pageHref, type Board, type Drill } from "@/lib/recruitmentDashboards";
import type { User } from "@/lib/types";

async function shell(user: User): Promise<{ nav: NavItem[]; roleLabel: string }> {
  if (user.role === "partner") {
    const me = await serverApi<ManagementMe>("/api/v1/management/me");
    return { nav: managementNavFor(me.tiers), roleLabel: MANAGEMENT_ROLE_LABEL[me.role] ?? me.role };
  }
  if (user.role === "hr_manager") return { nav: PORTAL_NAV["it/hr-manager"], roleLabel: "HR Manager" };
  if (user.role === "it_admin") return { nav: PORTAL_NAV["it/admin"], roleLabel: "IT Administrator" };
  return companyShell(user.role);
}

// hrc-033 (DEC-SCOPE-413 D10): the five operational recruitment dashboards. The API decides who reads them (`reports.recruitment`; anyone else
// 403, shown as the access card) and whose records are in scope. A bad range shows the API's words beside the form.
export default async function RecruitmentDashboardPage({ params, searchParams }: { params: Promise<{ board: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { board } = await params;
  if (!isBoard(board)) notFound();
  const search = await searchParams;
  const query = dashboardQuery(search);
  // The GET form sends every field; one redirect drops the empty ones so the address is short and shareable.
  if (Object.values(search).some((value) => value === "")) redirect(pageHref(board, query));
  let user: User;
  let frame: Awaited<ReturnType<typeof shell>>;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    frame = await shell(user);
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  let data: Board | null = null;
  let drill: Drill | null = null;
  let error = "";
  try {
    data = await serverApi<Board>(boardUrl(board, query));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/it/login");
    error = dashboardError(e);
  }
  if (data && query.drill) {
    try {
      drill = await serverApi<Drill>(drillUrl(board, query));
    } catch (e) {
      error = dashboardError(e);
    }
  }
  return (
    <PortalShell nav={frame.nav} roleLabel={frame.roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Recruitment dashboards</div>
            <h2>{data?.label ?? "Recruitment dashboards"}</h2>
          </div>
        </div>
        <RecruitmentDashboard board={board} data={data} drill={drill} error={error} query={query} />
      </div>
    </PortalShell>
  );
}

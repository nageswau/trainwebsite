import { accessUnavailable } from "@/components/AccessUnavailable";
import ItReportsWorkspace from "@/components/ItReportsWorkspace";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { IT_ADMIN_IT_REPORTS, MANAGEMENT_IT_REPORTS, itReport, itReportParams, itReportUrl, itReportsIndexUrl, type ItReport, type ItReportPage } from "@/lib/itReports";
import { MANAGEMENT_ROLE_LABEL, managementNavFor, type ManagementMe } from "@/lib/management";
import { PORTAL_NAV, SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import type { User } from "@/lib/types";

const UNAVAILABLE = "IT reports are unavailable right now. Please try again.";

// itc-032 (DEC-SCOPE-369 R6): one body behind management's /management/it-reports and the IT Admin's /it/admin/management-reports. The API
// lists the reports the caller may open (the accountant: Revenue only) and refuses the rest (403 -> the access card); a 422 (bad filters)
// is shown above the form. Each shell keeps its own sidebar; super_admin keeps theirs.
export default async function ItReportsPage({ shell, searchParams }: {
  shell: "it" | "management"; searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const search = await searchParams;
  const loginHref = shell === "it" ? "/it/login" : "/admin/login";
  let user: User;
  let nav: NavItem[];
  let roleLabel: string;
  let tabs: { key: ItReport; label: string }[];
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role === "super_admin") {
      [nav, roleLabel] = [SUPER_ADMIN_NAV, "Super Administrator"];
    } else if (shell === "management") {
      const me = await serverApi<ManagementMe>("/api/v1/management/me");
      [nav, roleLabel] = [managementNavFor(me.tiers), MANAGEMENT_ROLE_LABEL[me.role] ?? me.role];
    } else {
      [nav, roleLabel] = [PORTAL_NAV["it/admin"], "IT Administrator"];
    }
    tabs = (await serverApi<{ reports: { key: ItReport; label: string }[] }>(itReportsIndexUrl)).reports;
  } catch (e) {
    return accessUnavailable(e, loginHref);
  }
  const report = itReport(search.report, tabs.map((t) => t.key))!;
  const params = itReportParams(search);
  let page: ItReportPage | null = null;
  let error = "";
  try {
    page = await serverApi<ItReportPage>(itReportUrl(report, params));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, loginHref);
    error = e instanceof ApiError && e.status === 422 ? e.message : UNAVAILABLE;
  }
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">IT training</div>
            <h2>IT reports</h2>
            <p className="muted">Leads, conversions, fees, attendance, placement and team activity for IT training, with the same filters on every report. Dates are India time (IST); every figure adds up to the rows below it.</p>
          </div>
        </div>
        <ItReportsWorkspace report={report} tabs={tabs} page={page} error={error} params={params} basePath={shell === "it" ? IT_ADMIN_IT_REPORTS : MANAGEMENT_IT_REPORTS} />
      </div>
    </PortalShell>
  );
}

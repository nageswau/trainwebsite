import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import TelecallerReportView from "@/components/TelecallerReportView";
import { ApiError, serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import { type TelecallerReport, reportKind, reportParams, reportUrl } from "@/lib/telecallerReports";
import type { User } from "@/lib/types";

const UNAVAILABLE = "This report is unavailable right now. Please try again.";

// tel-024 (DEC-SCOPE-109, T24): the one body behind the manager's /telecaller/manager/reports and the admins' telecaller-reports pages.
// The API decides the scope (a manager's reports, an admin's division, everything for super_admin); the role check here only spares
// other roles a screen that can only fail. A 422 (bad dates) is shown above the form; a 403 is the access card.
export default async function TelecallerReportsPage({ roles, nav, roleLabel, loginHref, basePath, searchParams }: {
  roles: string[]; nav: NavItem[]; roleLabel: string; loginHref: string; basePath: string;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const search = await searchParams;
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, loginHref);
  }
  if (!roles.includes(user.role)) return accessDenied(user, `${roleLabel} role required`);
  const kind = reportKind(typeof search.report === "string" ? search.report : undefined);
  const params = reportParams(search);
  let report: TelecallerReport | null = null;
  let error = "";
  try {
    report = await serverApi<TelecallerReport>(reportUrl(kind, params));
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) return accessUnavailable(e, loginHref);
    error = e instanceof ApiError && e.status === 422 ? e.message : UNAVAILABLE;
  }
  // As AdminTelecallerPage: super_admin keeps their own sidebar on an admin page; on the manager page they see the manager's.
  const superAdmin = user.role === "super_admin" && !basePath.startsWith("/telecaller/");
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : nav} roleLabel={superAdmin ? "Super Administrator" : roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Telecaller CRM</div>
            <h2>Reports</h2>
            <p className="muted">Lead source, course, telecaller, counselor handover and campaign figures for a date range. Lead reports count leads created in the range; a lead counts in every stage it has reached. The Telecaller report counts the activity logged in the range.</p>
          </div>
        </div>
        <TelecallerReportView kind={kind} report={report} error={error} params={params} basePath={basePath} />
      </div>
    </PortalShell>
  );
}

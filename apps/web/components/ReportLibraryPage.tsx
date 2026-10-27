import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import ReportView, { ReportLibraryList } from "@/components/ReportView";
import { ApiError, serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import { type CatalogueItem, REPORTS_API, type Report, reportParams, reportUrl } from "@/lib/reports";
import type { User } from "@/lib/types";

const UNAVAILABLE = "This report is unavailable right now. Please try again.";

// nehn-009 (DEC-SCOPE-303): the one body behind every portal's Report library. The API decides which reports the caller may view (its
// grants) and which rows they see (the report's scope); the role check here only spares other roles a screen that can only fail. Without
// `?report=` it lists the reports; with one it shows that report. A 422 (bad filters) is shown above the form; a 403 is the access card.
export default async function ReportLibraryPage({ roles, nav, roleLabel, loginHref, basePath, searchParams }: {
  roles: string[]; nav: NavItem[]; roleLabel: string; loginHref: string; basePath: string;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const search = await searchParams;
  let user: User;
  let items: CatalogueItem[];
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, loginHref);
  }
  if (!roles.includes(user.role)) return accessDenied(user, `${roleLabel} role required`);
  try {
    items = (await serverApi<{ items: CatalogueItem[] }>(REPORTS_API)).items;
  } catch (e) {
    return accessUnavailable(e, loginHref);
  }
  const requested = typeof search.report === "string" ? search.report : undefined;
  const item = items.find((i) => i.id === requested);
  const params = item ? reportParams(search, item.filters) : {};
  let report: Report | null = null;
  let error = "";
  if (item) {
    try {
      report = await serverApi<Report>(reportUrl(item.id, params));
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) return accessUnavailable(e, loginHref);
      error = e instanceof ApiError && e.status === 422 ? e.message : UNAVAILABLE;
    }
  }
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : nav} roleLabel={superAdmin ? "Super Administrator" : roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Reports</div>
            <h2>Report library</h2>
            <p className="muted">Filter a report, page through it, and download every matching row as CSV or Excel. You see only the reports and rows your role allows.</p>
          </div>
        </div>
        {item ? (
          <ReportView item={item} report={report} error={error} params={params} basePath={basePath} />
        ) : (
          <div className="action-card">
            {requested && <p className="form-error" role="alert">That report isn&apos;t available to you.</p>}
            <ReportLibraryList items={items} basePath={basePath} />
          </div>
        )}
      </div>
    </PortalShell>
  );
}

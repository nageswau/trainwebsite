import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import CrossSchoolAnalytics from "@/components/CrossSchoolAnalytics";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { CrossSchoolSummary, SchoolUtilizationPage, User } from "@/lib/types";

// ENH-016 (School CRM.md §34 + §27, DEC-SCOPE-034 D1): Edusphere's view across every partner school. Admin-only, like the API
// (/overseas-admin/analytics/* answers 403 to any other role): the role is checked here first so nobody else is shown a
// screen that can only fail. A static route wins over `[section]`, like school-transfers. Each half is read on its own.
const ADMIN_ROLES = ["overseas_admin", "super_admin"];
const MAX_OFFSET = 10_000; // the API's bound: past it the table section could only fail (QA-016-07)

export default async function AdminSchoolAnalyticsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e);
  }
  if (!ADMIN_ROLES.includes(user.role)) return accessDenied(user, "Overseas Administrator role required");
  const sp = await searchParams;
  const one = (key: string) => (typeof sp[key] === "string" ? (sp[key] as string).trim() : "");
  const offset = Math.min(MAX_OFFSET, Math.max(0, Number.parseInt(one("offset"), 10) || 0));
  const q = one("q").slice(0, 200); // QA-016-09: the school search, same limit as the API
  const query = new URLSearchParams({ offset: String(offset) });
  if (q) query.set("q", q);
  const [summary, page] = await Promise.all([
    serverApi<CrossSchoolSummary>("/api/v1/overseas-admin/analytics/summary").catch(() => null),
    serverApi<SchoolUtilizationPage>(`/api/v1/overseas-admin/analytics/schools?${query}`).catch(() => null),
  ]);
  const superAdmin = user.role === "super_admin";
  return (
    // QA-016-08: a Super Admin keeps their own navigation (and its way back to /admin).
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : PORTAL_NAV["overseas/admin"]} roleLabel={superAdmin ? "Super Administrator" : "Overseas Administrator"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>School Analytics</h2>
            <p className="muted">Every partner school at a glance, and how much of each partnership is being used.</p>
          </div>
        </div>
        <CrossSchoolAnalytics summary={summary} page={page} basePath="/overseas/admin/school-analytics" q={q} />
      </div>
    </PortalShell>
  );
}

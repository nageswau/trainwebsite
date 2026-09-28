import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import CrossSchoolAnalytics from "@/components/CrossSchoolAnalytics";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import type { CrossSchoolSummary, SchoolUtilizationPage, User } from "@/lib/types";

// ENH-016 (School CRM.md §34 + §27, DEC-SCOPE-034 D1): Edusphere's view across every partner school. Admin-only, like the API
// (/overseas-admin/analytics/* answers 403 to any other role): the role is checked here first so nobody else is shown a
// screen that can only fail. A static route wins over `[section]`, like school-transfers. Each half is read on its own.
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function AdminSchoolAnalyticsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e);
  }
  if (!ADMIN_ROLES.includes(user.role)) return accessDenied(user, "Overseas Administrator role required");
  const raw = (await searchParams).offset;
  const offset = Math.max(0, Number.parseInt(typeof raw === "string" ? raw : "0", 10) || 0);
  const [summary, page] = await Promise.all([
    serverApi<CrossSchoolSummary>("/api/v1/overseas-admin/analytics/summary").catch(() => null),
    serverApi<SchoolUtilizationPage>(`/api/v1/overseas-admin/analytics/schools?offset=${offset}`).catch(() => null),
  ]);
  return (
    <PortalShell nav={PORTAL_NAV["overseas/admin"]} roleLabel={user.role === "super_admin" ? "Super Administrator" : "Overseas Administrator"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>School Analytics</h2>
            <p className="muted">Every partner school at a glance, and how much of each partnership is being used.</p>
          </div>
        </div>
        <CrossSchoolAnalytics summary={summary} page={page} basePath="/overseas/admin/school-analytics" />
      </div>
    </PortalShell>
  );
}

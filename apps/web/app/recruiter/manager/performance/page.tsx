import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterPerformancePanel from "@/components/RecruiterPerformancePanel";
import { ApiError, serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import { companyShell } from "@/lib/recruiterCompanies";
import { PERFORMANCE_URL, performanceError, performanceParams, performanceQuery, type Performance } from "@/lib/recruiterPerformance";
import { istToday } from "@/lib/telecallerTargets";
import type { User } from "@/lib/types";

const ROLES = ["placement_manager", "super_admin", "it_admin"]; // PF1
const UNASSIGNED_NOTE = "plus companies and requirements not yet given to a recruiter (Unassigned)";

// rec-033 (EVID-018 §24, DEC-SCOPE-182): the recruiter performance dashboard for the placement manager, super_admin and it_admin. The
// role check only spares other roles a screen that can only fail; the API decides whose figures are in scope (a recruiter outside the
// team → 404, said in place of the figures, with the way back to everyone).
export default async function RecruiterPerformancePage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = performanceParams(await searchParams);
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (!ROLES.includes(user.role)) return accessDenied(user, "Placement manager or administrator role required");
  let data: Performance | null = null;
  let error = "";
  try {
    data = await serverApi<Performance>(PERFORMANCE_URL + performanceQuery(params));
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) return accessUnavailable(e, "/admin/login");
    error = e instanceof ApiError && e.status === 404 ? "That recruiter is not in your team." : performanceError(e);
  }
  const { nav, roleLabel } = user.role === "it_admin" ? { nav: PORTAL_NAV["it/admin"], roleLabel: "IT Administrator" } : companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Performance</div>
            <h2>Recruiter performance</h2>
            <p className="muted">{user.role === "placement_manager" ? "Your team's" : "Every recruiter's"} results over a period, {UNASSIGNED_NOTE}. Ratios show &ldquo;—&rdquo; when there is nothing to divide by.</p>
          </div>
        </div>
        <RecruiterPerformancePanel data={data} error={error} params={params} today={istToday()} />
      </div>
    </PortalShell>
  );
}

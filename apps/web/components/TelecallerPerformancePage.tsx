import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import TelecallerPerformancePanel from "@/components/TelecallerPerformancePanel";
import { ApiError, serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import { PERFORMANCE_URL, performanceError, performanceParams, performanceQuery, type Performance } from "@/lib/telecallerPerformance";
import { istToday } from "@/lib/telecallerTargets";
import type { User } from "@/lib/types";

const MANAGERS = new Set(["telecaller_manager", "super_admin"]);
const DIVISION_ADMINS = new Set(["it_admin", "overseas_admin"]);

// tel-023 (PF1, T24): the one body behind /telecaller/manager/performance and the IT / Overseas / super admin pages. The role check only
// spares other roles a screen that can only fail; the API decides whose figures are in scope. `adminNav`: super_admin gets its own sidebar
// on an admin route (as AdminTelecallerPage); on the manager route it keeps the manager sidebar (as the activity page).
export default async function TelecallerPerformancePage({ roles, nav, roleLabel, loginHref, base, searchParams, adminNav = false }: {
  roles: string[]; nav: NavItem[]; roleLabel: string; loginHref: string; base: string;
  searchParams: Promise<Record<string, string | undefined>>; adminNav?: boolean;
}) {
  const params = performanceParams(await searchParams);
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, loginHref);
  }
  if (!roles.includes(user.role)) return accessDenied(user, `${roleLabel} role required`);
  let data: Performance | null = null;
  let error = "";
  try {
    data = await serverApi<Performance>(PERFORMANCE_URL + performanceQuery(params));
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) return accessUnavailable(e, loginHref);
    error = performanceError(e);
  }
  const superAdmin = adminNav && user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : nav} roleLabel={superAdmin ? "Super Administrator" : roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Performance</div>
            <h2>Compare telecallers</h2>
            <p className="muted">Leads received, calls, connected calls, qualified leads, appointments and conversions for each telecaller over a date range (up to 366 days).</p>
          </div>
        </div>
        <TelecallerPerformancePanel
          data={data} error={error} params={params} base={base} today={istToday()}
          teams={DIVISION_ADMINS.has(user.role) ? [] : ["it", "overseas"]}
          activityBase={MANAGERS.has(user.role) ? "/telecaller/manager/team" : undefined}
        />
      </div>
    </PortalShell>
  );
}

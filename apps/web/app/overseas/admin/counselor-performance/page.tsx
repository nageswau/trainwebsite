import { redirect } from "next/navigation";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import CounselorTeamPerformance from "@/components/CounselorTeamPerformance";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import {
  ADMIN_PERFORMANCE_API, ADMIN_PERFORMANCE_HOME, ADMIN_REFUSED, ADMIN_ROLES, TEAM_UNAVAILABLE, errorText, performanceQuery, performanceUrl, type TeamPerformance,
} from "@/lib/counselorPerformance";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ccrm-053 (DEC-SCOPE-325, PF5-PF7): the Overseas Admin's counselor performance -- every overseas counselor. Super Admin passes too (PF6);
// anyone else gets the access card; unauthenticated users are redirected by the middleware.

export default async function AdminCounselorPerformancePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const search = await searchParams;
  const query = performanceQuery(search);
  if (Object.values(search).some((value) => value === "")) redirect(performanceUrl(query, ADMIN_PERFORMANCE_HOME));
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e);
  }
  if (!ADMIN_ROLES.includes(user.role)) return accessDenied(user, ADMIN_REFUSED);
  let data: TeamPerformance | null = null;
  let error = "";
  try {
    data = await serverApi<TeamPerformance>(performanceUrl(query, ADMIN_PERFORMANCE_API));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e);
    error = errorText(e, TEAM_UNAVAILABLE);
  }
  return (
    <PortalShell nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>Counselor performance</h2>
            <p className="muted">Each overseas counselor&apos;s leads (Overseas and IT), conversions, students, applications, visas and enrolments. Open a counselor for their full report.</p>
          </div>
        </div>
        <CounselorTeamPerformance data={data} error={error} query={query} />
      </div>
    </PortalShell>
  );
}

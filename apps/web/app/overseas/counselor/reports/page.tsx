import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import CounselorPerformance from "@/components/CounselorPerformance";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { PERFORMANCE_UNAVAILABLE, performanceUrl, type CounselorPerformanceReport } from "@/lib/counselorPerformance";
import { counselingQuery } from "@/lib/managementCounseling";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ccrm-036 (DEC-SCOPE-269, P1): the overseas counselor's sidebar "Reports" -- their own performance report (it takes over the generic
// "My Caseload Report" section). Anyone else gets the access card; unauthenticated users are redirected by the middleware.
const REFUSED = "Only an overseas counselor has a performance report";

export default async function CounselorReportsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = counselingQuery(await searchParams);
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e);
  }
  if (user.role !== "counselor" || user.division !== "overseas") return accessDenied(user, REFUSED);
  let data: CounselorPerformanceReport | null = null;
  let error = "";
  try {
    data = await serverApi<CounselorPerformanceReport>(performanceUrl(query));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e);
    error = e instanceof ApiError && e.status === 422 && typeof e.message === "string" && !e.message.startsWith("[object") ? e.message : PERFORMANCE_UNAVAILABLE;
  }
  return (
    <PortalShell nav={PORTAL_NAV["overseas/counselor"]} roleLabel="Counselor" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>My performance</h2>
            <p className="muted">Your leads, follow-ups, tasks and conversions for a period, and your applications, offers, visas and enrolments now.</p>
          </div>
        </div>
        <CounselorPerformance data={data} error={error} query={query} />
      </div>
    </PortalShell>
  );
}

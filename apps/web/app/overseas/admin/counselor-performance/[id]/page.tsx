import Link from "next/link";
import { redirect } from "next/navigation";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import CounselorPerformance from "@/components/CounselorPerformance";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import {
  ADMIN_PERFORMANCE_API, ADMIN_PERFORMANCE_HOME, ADMIN_REFUSED, ADMIN_ROLES, TEAM_UNAVAILABLE, errorText, performanceQuery, performanceUrl,
  type CounselorPerformanceReport,
} from "@/lib/counselorPerformance";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ccrm-053 (DEC-SCOPE-323, PF5, PF6): one overseas counselor's own report (ccrm-036), read by the Overseas Admin with the list's filters.
// An id that is not an overseas counselor is the API's 404, said in words with the way back.
const NOT_FOUND = "This counselor was not found. They may not be an overseas counselor.";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function AdminCounselorReportPage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const search = await searchParams;
  const query = performanceQuery(search);
  const home = `${ADMIN_PERFORMANCE_HOME}/${encodeURIComponent(id)}`; // the address's own id, so a mistyped one stays in place
  if (Object.values(search).some((value) => value === "")) redirect(performanceUrl(query, home));
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e);
  }
  if (!ADMIN_ROLES.includes(user.role)) return accessDenied(user, ADMIN_REFUSED);
  let data: CounselorPerformanceReport | null = null;
  let error = "";
  if (!UUID.test(id)) {
    error = NOT_FOUND;
  } else {
    try {
      data = await serverApi<CounselorPerformanceReport>(performanceUrl(query, `${ADMIN_PERFORMANCE_API}/${id}`));
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e);
      error = e instanceof ApiError && e.status === 404 ? NOT_FOUND : errorText(e, TEAM_UNAVAILABLE);
    }
  }
  return (
    <PortalShell nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Counselor performance</div>
            <h2>{data?.counselor ? `${data.counselor.full_name}${data.counselor.active ? "" : " (inactive)"}` : "Counselor report"}</h2>
            <p className="muted"><Link href={performanceUrl(query, ADMIN_PERFORMANCE_HOME)}>Back to all counselors</Link></p>
          </div>
        </div>
        {error === NOT_FOUND ? (
          <div className="action-card"><p className="form-error" role="alert">{error}</p></div>
        ) : (
          <CounselorPerformance data={data} error={error} query={query} home={home} />
        )}
      </div>
    </PortalShell>
  );
}

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterComparisonPanel from "@/components/RecruiterComparisonPanel";
import { ApiError, serverApi } from "@/lib/api";
import { COMPARISON_URL, type Comparison } from "@/lib/recruiterComparison";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { performanceError, performanceParams, performanceQuery } from "@/lib/recruiterPerformance";
import { istToday } from "@/lib/telecallerTargets";
import type { User } from "@/lib/types";

const CREDIT = "Each figure counts for whoever did the work, so it stays with them after a company or requirement is reassigned.";
const INTRO: Record<string, string> = {
  placement_team: "Your business development and recruitment over a period.",
  placement_manager: "Your team's business development and recruitment side by side over a period, so no one is measured on calls alone.",
  super_admin: "Every recruiter's business development and recruitment side by side over a period, so no one is measured on calls alone.",
};

// rec-034 (EVID-018 §25, DEC-SCOPE-183): Recruiter/BDM performance per recruiter. The API is the gate (BP1): a recruiter reads only their
// own row, a placement manager their team, super_admin everyone; any other role gets its 403 message here. A recruiter outside the team
// (404) is said in place of the table, with the way back to everyone.
export default async function RecruiterComparisonPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = performanceParams(await searchParams);
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const own = user.role === "placement_team";
  let data: Comparison | null = null;
  let error = "";
  try {
    data = await serverApi<Comparison>(COMPARISON_URL + performanceQuery(own ? { from: params.from, to: params.to } : params));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, RECRUITER_SIGN_IN);
    error = e instanceof ApiError && e.status === 404 ? "That recruiter is not in your team." : performanceError(e);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Performance</div>
            <h2>{own ? "My performance" : "Recruiter comparison"}</h2>
            <p className="muted">{INTRO[user.role] ?? INTRO.super_admin} {CREDIT}</p>
          </div>
        </div>
        <RecruiterComparisonPanel data={data} error={error} params={own ? { from: params.from, to: params.to } : params} today={istToday()} own={own} />
      </div>
    </PortalShell>
  );
}

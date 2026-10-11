import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterDashboardTiles from "@/components/RecruiterDashboardTiles";
import RecruiterProfileCard from "@/components/RecruiterProfileCard";
import RecruiterQuickActions from "@/components/RecruiterQuickActions";
import RecruiterRecruiterFilter from "@/components/RecruiterRecruiterFilter";
import RecruiterSkillSearch from "@/components/RecruiterSkillSearch";
import { ApiError, serverApi } from "@/lib/api";
import { formatCalendarDate } from "@/lib/formatDate";
import type { RecruiterMe, RecruiterTeamRow } from "@/lib/recruiter";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { dashboardUrl, type RecruiterDashboard } from "@/lib/recruiterDashboard";
import type { User } from "@/lib/types";

const TEAM_URL = "/api/v1/recruiter/manager/team?limit=100";
const INTRO: Record<string, string> = {
  placement_team: "Your figures, worked out from your companies, requirements and candidates. Select a figure to open its list.",
  placement_manager: "Your team's figures, plus new companies and requirements waiting for a recruiter. Select a figure to open its list.",
  super_admin: "Every recruiter's figures. Select a figure to open its list.",
};

// rec-001 (AC3) + rec-032 (DEC-SCOPE-177): the recruiter dashboard -- the §1 tiles for the caller's scope, the quick actions and the
// one-click skill search. The API is the gate: any other role (hr_team included, Q-28), or a recruiter without a profile, gets its 403
// message here. A manager or super_admin may narrow to one recruiter (`?recruiter=`); one outside their team says so in place of the tiles.
export default async function RecruiterDashboardPage({ searchParams }: { searchParams: Promise<{ recruiter?: string }> }) {
  const recruiter = (await searchParams).recruiter?.trim() || null;
  const [me, read] = await Promise.allSettled([serverApi<User>("/api/v1/auth/me"), serverApi<RecruiterDashboard>(dashboardUrl(recruiter))]);
  if (me.status === "rejected") return accessUnavailable(me.reason, RECRUITER_SIGN_IN);
  const failure = read.status === "rejected" ? read.reason : null;
  if (failure instanceof ApiError && (failure.status === 401 || failure.status === 403)) return accessUnavailable(failure, RECRUITER_SIGN_IN);
  const user = me.value;
  const dashboard = read.status === "fulfilled" ? read.value : null;
  const notInTeam = recruiter && failure instanceof ApiError && (failure.status === 404 || failure.status === 422);
  const isRecruiter = user.role === "placement_team";
  const [profile, team] = await Promise.all([
    isRecruiter ? serverApi<RecruiterMe>("/api/v1/recruiter/me").catch(() => null) : null,
    isRecruiter ? null : serverApi<{ items: RecruiterTeamRow[] }>(TEAM_URL).then((p) => p.items, () => null),
  ]);
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Recruiter dashboard</div>
            <h2>Welcome, {user.full_name}</h2>
            <p className="muted">{dashboard?.recruiter ? `${dashboard.recruiter.full_name}'s figures. Select a figure to open its list.` : INTRO[user.role]}</p>
            {dashboard && (
              <p className="muted" style={{ margin: 0 }}>
                Today is {formatCalendarDate(dashboard.day)} (IST). Monthly figures count from {formatCalendarDate(dashboard.period.from)}.
              </p>
            )}
          </div>
        </div>
        {team && team.length > 0 && <RecruiterRecruiterFilter team={team} selected={notInTeam ? "" : recruiter ?? ""} />}
        <RecruiterDashboardTiles dashboard={dashboard} error={notInTeam ? "That recruiter is not in your team. Choose Whole team or one of your recruiters." : undefined} />
        <RecruiterQuickActions role={user.role} />
        <RecruiterSkillSearch />
        {profile && <RecruiterProfileCard me={profile} />}
      </div>
    </PortalShell>
  );
}

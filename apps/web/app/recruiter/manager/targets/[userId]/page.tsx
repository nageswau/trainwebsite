import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import PoTargetCompanies from "@/components/PoTargetCompanies";
import TargetsEditor from "@/components/TargetsEditor";
import { ApiError, serverApi } from "@/lib/api";
import { chosenMonth, currentMonth, monthLabel } from "@/lib/bdmTargets";
import { isUuid } from "@/lib/bdmTravel";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { MANAGER_TARGETS_PATH, type PoSheet, rateText, TEAM_TARGETS_URL } from "@/lib/recruiterPoWork";
import type { User } from "@/lib/types";

// pob-009 T3-T5: one placement officer's month for the Team Lead -- targets (editable while the month is), territory and target companies.
export default async function MemberTargetsPage({ params, searchParams }: { params: Promise<{ userId: string }>; searchParams: Promise<{ month?: string }> }) {
  const { userId } = await params;
  const { month, note } = chosenMonth((await searchParams).month, currentMonth());
  let user: User;
  let sheet: PoSheet | null = null;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "placement_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for Team Leads.");
    if (!isUuid(userId)) return accessDenied(user, "Placement officer not found");
    sheet = await serverApi<PoSheet>(`${TEAM_TARGETS_URL}/${userId}?month=${month}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return accessDenied(user!, "That placement officer is not in your team.");
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Targets</div>
            <h2>{sheet.recruiter.full_name} — {monthLabel(sheet.month)}</h2>
            <p className="muted">Response rate {rateText(sheet.response_rate)} · <a href={`${MANAGER_TARGETS_PATH}?month=${sheet.month}`}>All placement officers</a></p>
            {note && <p className="muted">{note}</p>}
            {!sheet.editable && <p className="muted">{sheet.month_status === "past" ? "Past months are read-only." : "These targets can't be changed."}</p>}
          </div>
        </div>
        <TargetsEditor key={`${sheet.recruiter.id}-${sheet.month}`} initial={sheet} ownerId={sheet.recruiter.id} ownerField="recruiter_user_id" saveUrl={TEAM_TARGETS_URL} />
        <PoTargetCompanies sheet={sheet} manage />
      </div>
    </PortalShell>
  );
}

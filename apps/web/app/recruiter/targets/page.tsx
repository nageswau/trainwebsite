import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import PoTargetCompanies from "@/components/PoTargetCompanies";
import TargetsEditor from "@/components/TargetsEditor";
import { serverApi } from "@/lib/api";
import { chosenMonth, currentMonth, monthLabel, monthOptions } from "@/lib/bdmTargets";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { MY_TARGETS_URL, type PoSheet, rateText, TEAM_TARGETS_URL } from "@/lib/recruiterPoWork";
import type { User } from "@/lib/types";

// pob-009 T3 (AC2): the PO's month -- each KPI's target from their Team Lead against the live actual, the response rate, their territory
// and target companies. Read only; the Team Lead sets them.
export default async function MyTargetsPage({ searchParams }: { searchParams: Promise<{ month?: string }> }) {
  const current = currentMonth();
  const { month, note } = chosenMonth((await searchParams).month, current);
  let user: User, sheet: PoSheet;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "placement_team") return accessDenied(user, "This page is for placement officers.");
    sheet = await serverApi<PoSheet>(`${MY_TARGETS_URL}?month=${month}`);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Targets</div>
            <h2>My targets — {monthLabel(sheet.month)}</h2>
            <p className="muted">Set by your Team Lead. Achieved counts what you did this month; response rate: {rateText(sheet.response_rate)}
              {sheet.contacts_reached !== null && ` of ${sheet.contacts_reached} contacts reached`}.</p>
            <form className="analytics-form" method="get" action="/recruiter/targets" aria-label="Choose a month">
              <div className="field">
                <label htmlFor="targets-month">Month</label>
                <select id="targets-month" name="month" defaultValue={month}>
                  {monthOptions(current).map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </div>
              <button className="btn secondary" type="submit">Show</button>
            </form>
            {note && <p className="muted">{note}</p>}
          </div>
        </div>
        <TargetsEditor key={sheet.month} initial={sheet} ownerId={sheet.recruiter.id} ownerField="recruiter_user_id" saveUrl={TEAM_TARGETS_URL} />
        <PoTargetCompanies sheet={sheet} manage={false} />
      </div>
    </PortalShell>
  );
}

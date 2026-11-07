import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { chosenMonth, currentMonth, monthLabel, monthOptions, TEAM_PAGE } from "@/lib/bdmTargets";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { cellText, MANAGER_TARGETS_PATH, rateText, TEAM_TARGETS_URL, type TeamTargets } from "@/lib/recruiterPoWork";
import type { User } from "@/lib/types";

// pob-009 T3 (AC2): the Team Lead's month -- each placement officer's actual / target per KPI; open one to set targets, territory and
// target companies.
export default async function TeamTargetsPage({ searchParams }: { searchParams: Promise<{ month?: string; offset?: string }> }) {
  const sp = await searchParams;
  const current = currentMonth();
  const { month, note } = chosenMonth(sp.month, current);
  const offset = Math.max(0, Number.parseInt(sp.offset ?? "0", 10) || 0);
  let user: User, team: TeamTargets;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "placement_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for Team Leads.");
    team = await serverApi<TeamTargets>(`${TEAM_TARGETS_URL}?month=${month}&limit=${TEAM_PAGE}&offset=${offset}`);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  const page = (to: number) => `${MANAGER_TARGETS_PATH}?month=${month}&offset=${to}`;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Targets</div>
            <h2>Placement officer targets — {monthLabel(month)}</h2>
            <p className="muted">Each cell is achieved / target (achievement). Achieved counts what the officer did this month. Open an officer to set targets, territory and target companies.</p>
            <form className="analytics-form" method="get" action={MANAGER_TARGETS_PATH} aria-label="Choose a month">
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
        {team.items.length === 0 ? (
          <p className="empty">No active placement officers report to you yet.</p>
        ) : (
          <div className="table-scroll" role="region" aria-labelledby="po-targets-caption" tabIndex={0}>
            <table className="table">
              <caption id="po-targets-caption" className="visually-hidden">Achieved and targets by placement officer for {monthLabel(month)}</caption>
              <thead>
                <tr>
                  <th scope="col">Placement officer</th>
                  {team.kpis.map((k) => <th scope="col" key={k.key}>{k.label}</th>)}
                  <th scope="col">Response rate</th>
                </tr>
              </thead>
              <tbody>
                {team.items.map((row) => (
                  <tr key={row.recruiter.id}>
                    <th scope="row">
                      <a href={`${MANAGER_TARGETS_PATH}/${row.recruiter.id}?month=${month}`} title={team.editable ? "Set targets" : "View targets"} style={LINK_STYLE}>{row.recruiter.full_name}</a>
                      {row.territory && <span className="kpi-note muted">{row.territory}</span>}
                    </th>
                    {row.kpis.map((k) => <td key={k.key}>{cellText(k, team.month_status)}</td>)}
                    <td>{rateText(row.response_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {team.total > team.limit && (
          <nav className="pager" aria-label="Placement officer pages">
            {offset > 0 && <a className="btn secondary small" href={page(Math.max(0, offset - team.limit))}>Previous</a>}
            <span className="muted">Officers {offset + 1}–{Math.min(offset + team.limit, team.total)} of {team.total}</span>
            {offset + team.limit < team.total && <a className="btn secondary small" href={page(offset + team.limit)}>Next</a>}
          </nav>
        )}
      </div>
    </PortalShell>
  );
}

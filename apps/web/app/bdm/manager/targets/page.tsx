import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmTargetsCopy from "@/components/BdmTargetsCopy";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL } from "@/lib/bdm";
import { bdmManagerNav } from "@/lib/bdmNav";
import { chosenMonth, currentMonth, MANAGER_TARGETS_PATH, monthLabel, monthOptions, TEAM_PAGE, TEAM_TARGETS_URL, type TeamTargets, teamTargetHref } from "@/lib/bdmTargets";
import type { User } from "@/lib/types";

// bdm-016 (spec §6): the team's monthly targets -- each active BDM with how many of their KPIs have a target; open one to set them.
// The month lives in the URL (a plain GET form); Copy fills this month's missing targets from last month's.
export default async function ManagerTargetsPage({ searchParams }: { searchParams: Promise<{ month?: string; offset?: string }> }) {
  const nav = bdmManagerNav();
  const sp = await searchParams;
  const current = currentMonth();
  const { month, note } = chosenMonth(sp.month, current);
  const offset = Math.max(0, Number.parseInt(sp.offset ?? "0", 10) || 0);
  let user: User, team: TeamTargets;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
    team = await serverApi<TeamTargets>(`${TEAM_TARGETS_URL}?month=${month}&limit=${TEAM_PAGE}&offset=${offset}`);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const page = (to: number) => `${MANAGER_TARGETS_PATH}?month=${month}&offset=${to}`;
  return (
    <PortalShell nav={await nav} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Targets</div>
            <h2>Team targets — {monthLabel(month)}</h2>
            <p className="muted">Set each BDM&apos;s monthly target per KPI. Achieved is counted from what the BDM recorded that month.</p>
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
            {!team.editable && <p className="muted">{team.month_status === "past" ? "Past months are read-only." : "Targets can be set up to 12 months ahead."}</p>}
          </div>
        </div>
        {team.editable && <BdmTargetsCopy month={month} />}
        {team.items.length === 0 ? (
          <p className="empty">No active BDMs report to you yet.</p>
        ) : (
          <div className="table-scroll" role="region" aria-labelledby="team-targets-caption" tabIndex={0}>
            <table className="table">
              <caption id="team-targets-caption" className="visually-hidden">Targets set by BDM for {monthLabel(month)}</caption>
              <thead><tr><th scope="col">BDM</th><th scope="col">Targets set</th><th scope="col"><span className="visually-hidden">Open</span></th></tr></thead>
              <tbody>
                {team.items.map((row) => (
                  <tr key={row.bdm.id}>
                    <th scope="row">{row.bdm.full_name}<span className="kpi-note muted">{BDM_TYPE_LABEL[row.bdm_type]} BDM</span></th>
                    <td>{row.targets_set} of {row.kpi_count}</td>
                    <td>
                      <a className="btn secondary small" href={teamTargetHref(row.bdm.id, month)} aria-label={`${team.editable ? "Set" : "View"} targets for ${row.bdm.full_name}`}>
                        {team.editable ? "Set targets" : "View"}
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {team.total > team.limit && (
          <nav className="pager" aria-label="BDM pages">
            {offset > 0 && <a className="btn secondary small" href={page(Math.max(0, offset - team.limit))}>Previous</a>}
            <span className="muted">BDMs {offset + 1}–{Math.min(offset + team.limit, team.total)} of {team.total}</span>
            {offset + team.limit < team.total && <a className="btn secondary small" href={page(offset + team.limit)}>Next</a>}
          </nav>
        )}
      </div>
    </PortalShell>
  );
}

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { activityDay } from "@/lib/bdmActivities";
import { BDM_TYPE_LABEL } from "@/lib/bdm";
import { GRID_STATUS_LABEL, TEAM_PAGE, TEAM_REPORTS_URL, type TeamGrid, teamReportHref } from "@/lib/bdmDailyReports";
import { bdmManagerNav } from "@/lib/bdmNav";
import { indiaToday } from "@/lib/bdmTravel";
import { formatSchoolDateTime } from "@/lib/formatDate";
import type { User } from "@/lib/types";

const PATH = "/bdm/manager/daily-reports";
// A grid column heading: weekday + day + month of a calendar date (formatted in UTC, the formatCalendarDate rule).
const columnDate = (day: string) => new Date(`${day}T00:00:00Z`).toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", timeZone: "UTC" });

// bdm-015 (spec §6, R8): who has submitted the daily report -- the team's active BDMs × the seven days ending on the chosen date.
// Submitted and Missing are words, not colours; each opens that report. "—" is a day before the BDM's profile existed.
export default async function ManagerDailyReportsPage({ searchParams }: { searchParams: Promise<{ date?: string; offset?: string }> }) {
  const nav = bdmManagerNav();
  const sp = await searchParams;
  const today = indiaToday();
  const { day, note } = activityDay(sp.date, today);
  const offset = Math.max(0, Number.parseInt(sp.offset ?? "0", 10) || 0);
  let user: User, grid: TeamGrid;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
    grid = await serverApi<TeamGrid>(`${TEAM_REPORTS_URL}?date=${day}&limit=${TEAM_PAGE}&offset=${offset}`);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const page = (to: number) => `${PATH}?date=${day}&offset=${to}`;
  return (
    <PortalShell nav={await nav} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Daily reports</div>
            <h2>Team daily reports</h2>
            <p className="muted">Who submitted the end-of-day report in the seven days up to the chosen date. Open a report to read it or comment.</p>
            <form className="analytics-form" method="get" action={PATH} aria-label="Choose the last day">
              <div className="field">
                <label htmlFor="team-report-date">Up to</label>
                <input id="team-report-date" type="date" name="date" defaultValue={day} max={today} />
              </div>
              <button className="btn secondary" type="submit">Show</button>
            </form>
            {note && <p className="muted">{note}</p>}
          </div>
        </div>
        {grid.items.length === 0 ? (
          <p className="empty">No active BDMs report to you yet.</p>
        ) : (
          <div className="table-scroll" role="region" aria-labelledby="team-reports-caption" tabIndex={0}>
            <table className="table">
              <caption id="team-reports-caption" className="visually-hidden">Daily report status by BDM and day</caption>
              <thead>
                <tr>
                  <th scope="col">BDM</th>
                  {grid.dates.map((d) => <th scope="col" key={d}>{columnDate(d)}</th>)}
                </tr>
              </thead>
              <tbody>
                {grid.items.map((row) => (
                  <tr key={row.bdm.id}>
                    <th scope="row">{row.bdm.full_name}<span className="kpi-note muted">{BDM_TYPE_LABEL[row.bdm_type]} BDM</span></th>
                    {row.days.map((cell) => (
                      <td key={cell.report_date}>
                        {cell.status === "not_started" ? (
                          <span aria-label="Not started">{GRID_STATUS_LABEL.not_started}</span>
                        ) : (
                          <a href={teamReportHref(row.bdm.id, cell.report_date)} className="state-badge"
                            title={cell.submitted_at ? `Submitted ${formatSchoolDateTime(cell.submitted_at, true)}` : undefined}>
                            {cell.status === "submitted" ? "✓ " : ""}{GRID_STATUS_LABEL[cell.status]}
                          </a>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {grid.total > grid.limit && (
          <nav className="pager" aria-label="BDM pages">
            {offset > 0 && <a className="btn secondary small" href={page(Math.max(0, offset - grid.limit))}>Previous</a>}
            <span className="muted">BDMs {offset + 1}–{Math.min(offset + grid.limit, grid.total)} of {grid.total}</span>
            {offset + grid.limit < grid.total && <a className="btn secondary small" href={page(offset + grid.limit)}>Next</a>}
          </nav>
        )}
      </div>
    </PortalShell>
  );
}

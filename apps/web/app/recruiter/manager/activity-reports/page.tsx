import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PoPeriodPicker from "@/components/PoPeriodPicker";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { chosenPeriod, MANAGER_REPORTS_PATH, periodLabel, rateText, type TeamReports, teamReportsUrl } from "@/lib/recruiterPoWork";
import { istToday } from "@/lib/telecallerTargets";
import type { User } from "@/lib/types";

// pob-009 T7: the Team Lead's view of the team's daily or weekly reports -- submitted (with headline figures) or missing.
export default async function TeamReportsPage({ searchParams }: { searchParams: Promise<{ period?: string; start?: string }> }) {
  const today = istToday();
  const { period, start } = chosenPeriod(await searchParams, today);
  let user: User, grid: TeamReports;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "placement_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for Team Leads.");
    grid = await serverApi<TeamReports>(`${teamReportsUrl(period, start)}&limit=100`);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Activity reports</div>
            <h2>Team {period === "weekly" ? "weekly" : "daily"} reports — {periodLabel(period, grid.period_start, grid.period_end)}</h2>
            <PoPeriodPicker action={MANAGER_REPORTS_PATH} period={period} start={start} today={today} />
          </div>
        </div>
        {grid.items.length === 0 ? (
          <p className="empty">No active placement officers report to you yet.</p>
        ) : (
          <div className="table-scroll" role="region" aria-label="Team reports" tabIndex={0}>
            <table className="table compact stack">
              <thead><tr><th scope="col">Placement officer</th><th scope="col">Status</th><th scope="col">Outreach</th><th scope="col">Response rate</th><th scope="col">Meetings</th><th scope="col"><span className="visually-hidden">Open</span></th></tr></thead>
              <tbody>
                {grid.items.map((row) => (
                  <tr key={row.recruiter.id}>
                    <th scope="row">{row.recruiter.full_name}</th>
                    <td><span className={`badge ${row.status === "submitted" ? "success" : "warning"}`}>{row.status === "submitted" ? "Submitted" : "Missing"}</span></td>
                    <td>{row.outreach ?? "—"}</td>
                    <td>{row.status === "submitted" ? rateText(row.response_rate) : "—"}</td>
                    <td>{row.meetings ?? "—"}</td>
                    <td><a className="btn secondary small" href={`${MANAGER_REPORTS_PATH}/${row.recruiter.id}?period=${period}&start=${grid.period_start}`}
                      aria-label={`Open ${row.recruiter.full_name}'s report`}>Open</a></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PortalShell>
  );
}

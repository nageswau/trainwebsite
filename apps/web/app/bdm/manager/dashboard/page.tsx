import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmManagerDashboard from "@/components/BdmManagerDashboard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import type { BdmManagerOption, BdmTeamRow } from "@/lib/bdm";
import { dashboardUrl, isManagerDashboard, type ManagerDashboard } from "@/lib/bdmManagerDashboard";
import { bdmManagerNav } from "@/lib/bdmNav";
import { isUuid } from "@/lib/bdmTravel";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

const PATH = "/bdm/manager/dashboard";

function teamSummary(team: Page<BdmTeamRow>): string {
  const active = team.items.filter((r) => r.active).length;
  const inactive = team.items.length - active;
  return team.total === 0
    ? "No BDMs report to you yet."
    : `${team.total} BDM${team.total === 1 ? " reports" : "s report"} to you: ${active} active, ${inactive} inactive${team.total > team.items.length ? " on the first page" : ""}.`;
}

// bdm-001 (AC05, B2): the manager landing page -- team counts. bdm-023 (DEC-SCOPE-104): the management dashboard below them -- the
// §13 overview tiles and the alerts. A super_admin (R1, R2) keeps the admin navigation and may narrow to one manager's team; a dashboard
// that can't be read after the gate is shown inline with "Try again".
export default async function BdmManagerDashboardPage({ searchParams }: { searchParams: Promise<{ manager?: string }> }) {
  const requested = (await searchParams).manager;
  const managerId = requested && isUuid(requested) ? requested : undefined;
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const superAdmin = user.role === "super_admin";
  const dashboard = serverApi<ManagerDashboard>(dashboardUrl(superAdmin ? managerId : undefined)).then((d) => (isManagerDashboard(d) ? d : null), () => null);
  let team: Page<BdmTeamRow> | null = null;
  let managers: BdmManagerOption[] = [];
  if (superAdmin) {
    managers = await serverApi<Page<BdmManagerOption>>("/api/v1/admin/bdm-managers?limit=100").then((p) => p.items, () => []);
  } else {
    try {
      team = await serverApi<Page<BdmTeamRow>>("/api/v1/bdm/manager/team?limit=50");
    } catch (e) {
      return accessUnavailable(e, "/admin/login");
    }
  }
  const data = await dashboard;
  const chosen = data?.manager?.full_name;
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : await bdmManagerNav()} roleLabel={superAdmin ? "Super Administrator" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Dashboard</div>
            <h2>{superAdmin ? (chosen ? `${chosen}'s team` : "All BDM teams") : "Your team"}</h2>
            {team && <p className="muted">{teamSummary(team)}</p>}
          </div>
        </div>
        {superAdmin ? (
          <form method="get" action={PATH} className="actions" style={{ alignItems: "flex-end", marginBottom: 16 }}>
            <label>
              <span className="muted" style={{ display: "block" }}>Team</span>
              <select name="manager" defaultValue={managerId ?? ""}>
                <option value="">All teams</option>
                {managers.map((m) => <option key={m.id} value={m.id}>{m.full_name} ({m.email})</option>)}
              </select>
            </label>
            <button type="submit" className="btn secondary small">Show</button>
          </form>
        ) : (
          team && team.total > 0 && <p><Link className="btn" href="/bdm/manager/team">View team</Link></p>
        )}
        {data ? (
          <BdmManagerDashboard data={data} superAdmin={superAdmin} />
        ) : (
          <div className="card" role="alert">
            <p className="form-error">Unable to load the dashboard.</p>
            <a href={managerId && superAdmin ? `${PATH}?manager=${managerId}` : PATH} className="btn secondary small">Try again</a>
          </div>
        )}
      </div>
    </PortalShell>
  );
}

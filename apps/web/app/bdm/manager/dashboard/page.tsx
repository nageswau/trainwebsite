import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import type { BdmTeamRow } from "@/lib/bdm";
import { BDM_MANAGER_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// bdm-001 (AC05, B2): the manager landing page -- team counts; bdm-023 adds the management dashboard. Counts beyond the first page
// say so rather than guess.
export default async function BdmManagerDashboardPage() {
  let user: User, team: Page<BdmTeamRow>;
  try {
    [user, team] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Page<BdmTeamRow>>("/api/v1/bdm/manager/team?limit=50")]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const active = team.items.filter((r) => r.active).length;
  const inactive = team.items.length - active;
  const summary = team.total === 0
    ? "No BDMs report to you yet."
    : `${team.total} BDM${team.total === 1 ? " reports" : "s report"} to you: ${active} active, ${inactive} inactive${team.total > team.items.length ? " on the first page" : ""}.`;
  return (
    <PortalShell nav={BDM_MANAGER_NAV} roleLabel="BDM Manager" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Dashboard</div>
            <h2>Your team</h2>
            <p className="muted">{summary}</p>
          </div>
        </div>
        {team.total > 0 && <Link className="btn" href="/bdm/manager/team">View team</Link>}
      </div>
    </PortalShell>
  );
}

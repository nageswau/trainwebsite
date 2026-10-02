import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmTeamTable from "@/components/BdmTeamTable";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { PAGE_SIZE, type BdmTeamRow } from "@/lib/bdm";
import { BDM_MANAGER_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// bdm-001 (AC06): exactly the BDMs who report to this manager (the API scopes it). The offset lives in the URL.
export default async function BdmManagerTeamPage({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  const raw = Number.parseInt((await searchParams).offset ?? "0", 10);
  const offset = Number.isFinite(raw) && raw > 0 ? raw : 0;
  let user: User, team: Page<BdmTeamRow>;
  try {
    [user, team] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Page<BdmTeamRow>>(`/api/v1/bdm/manager/team?limit=${PAGE_SIZE}&offset=${offset}`),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={BDM_MANAGER_NAV} roleLabel="BDM Manager" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Team</div>
            <h2>BDMs who report to you</h2>
          </div>
        </div>
        {team.total === 0 ? <p className="empty" role="status">No BDMs report to you yet.</p> : <BdmTeamTable page={team} />}
      </div>
    </PortalShell>
  );
}

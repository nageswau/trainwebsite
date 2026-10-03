import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmTeamTable from "@/components/BdmTeamTable";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { PAGE_SIZE, type BdmTeamRow, pageOffset } from "@/lib/bdm";
import { bdmManagerNav } from "@/lib/bdmNav";
import type { User } from "@/lib/types";

// bdm-001 (AC06): exactly the BDMs who report to this manager (the API scopes it). The offset lives in the URL.
export default async function BdmManagerTeamPage({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  const nav = bdmManagerNav(); // the unread badge, read alongside the page's own data (never rejects)
  const offset = pageOffset((await searchParams).offset);
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
    <PortalShell nav={await nav} roleLabel="BDM Manager" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Team</div>
            <h2>BDMs who report to you</h2>
          </div>
        </div>
        {team.total === 0 ? (
          <p className="empty" role="status">No BDMs report to you yet.</p>
        ) : team.items.length === 0 ? (
          // QA-14: an ?offset= past the last row (an old link, or one edited by hand) offers a way back, not an empty table.
          <>
            <p className="empty" role="status">This page is past the end of your team.</p>
            <Link className="btn secondary small" href="/bdm/manager/team">Go to the first page</Link>
          </>
        ) : (
          <BdmTeamTable page={team} />
        )}
      </div>
    </PortalShell>
  );
}

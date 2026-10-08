import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PartnershipTeamTable from "@/components/PartnershipTeamTable";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { PARTNERSHIP_HEAD_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { ROLE_LABEL, TEAM_PATH, type PartnershipTeamRow } from "@/lib/partnership";
import { PAGE_SIZE, pageOffset } from "@/lib/telecaller";
import type { User } from "@/lib/types";

// upc-001 (AC4): exactly the partnership managers who report to this head (the API scopes it; super_admin sees all). The offset lives
// in the URL.
export default async function PartnershipHeadTeamPage({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  const offset = pageOffset((await searchParams).offset);
  let user: User, team: Page<PartnershipTeamRow>;
  try {
    [user, team] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Page<PartnershipTeamRow>>(`/api/v1/partnership/head/team?limit=${PAGE_SIZE}&offset=${offset}`),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : PARTNERSHIP_HEAD_NAV} roleLabel={superAdmin ? "Super Administrator" : ROLE_LABEL.head} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Team</div>
            <h2>{superAdmin ? "All partnership managers" : "Partnership managers who report to you"}</h2>
          </div>
        </div>
        {team.total === 0 ? (
          <p className="empty" role="status">{superAdmin ? "No partnership managers yet." : "No partnership managers report to you yet."}</p>
        ) : team.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of your team.</p>
            <Link className="btn secondary small" href={TEAM_PATH}>Go to the first page</Link>
          </>
        ) : (
          <PartnershipTeamTable page={team} />
        )}
      </div>
    </PortalShell>
  );
}

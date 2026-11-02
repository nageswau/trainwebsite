import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import TelecallerTeamTable from "@/components/TelecallerTeamTable";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { PAGE_SIZE, pageOffset, type TelecallerTeamRow } from "@/lib/telecaller";
import { telecallerManagerNav } from "@/lib/telecallerNav";
import type { User } from "@/lib/types";

// tel-001 (AC4, T23): exactly the telecallers who report to this manager (the API scopes it). The offset lives in the URL.
export default async function TelecallerManagerTeamPage({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  const offset = pageOffset((await searchParams).offset);
  const nav = telecallerManagerNav(); // itc-009: the sign-in landing shows the unread escalations (never rejects)
  let user: User, team: Page<TelecallerTeamRow>;
  try {
    [user, team] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Page<TelecallerTeamRow>>(`/api/v1/telecaller/manager/team?limit=${PAGE_SIZE}&offset=${offset}`),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={await nav} roleLabel="Telecaller Manager" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Team</div>
            <h2>Telecallers who report to you</h2>
          </div>
        </div>
        {team.total === 0 ? (
          <p className="empty" role="status">No telecallers report to you yet.</p>
        ) : team.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of your team.</p>
            <Link className="btn secondary small" href="/telecaller/manager/team">Go to the first page</Link>
          </>
        ) : (
          <TelecallerTeamTable page={team} />
        )}
      </div>
    </PortalShell>
  );
}

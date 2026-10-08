import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterTeamTable from "@/components/RecruiterTeamTable";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { RECRUITER_MANAGER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { PLACEMENT_MANAGER_LABEL, type RecruiterTeamRow } from "@/lib/recruiter";
import { PAGE_SIZE, pageOffset } from "@/lib/telecaller";
import type { User } from "@/lib/types";

// rec-001 (AC4): exactly the recruiters who report to this manager (the API scopes it; super_admin sees all). The offset lives in the URL.
export default async function RecruiterManagerTeamPage({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  const offset = pageOffset((await searchParams).offset);
  let user: User, team: Page<RecruiterTeamRow>;
  try {
    [user, team] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Page<RecruiterTeamRow>>(`/api/v1/recruiter/manager/team?limit=${PAGE_SIZE}&offset=${offset}`),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : RECRUITER_MANAGER_NAV} roleLabel={superAdmin ? "Super Administrator" : PLACEMENT_MANAGER_LABEL} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Team</div>
            <h2>{superAdmin ? "All recruiters" : "Recruiters who report to you"}</h2>
          </div>
        </div>
        {team.total === 0 ? (
          <p className="empty" role="status">{superAdmin ? "No recruiters yet." : "No recruiters report to you yet."}</p>
        ) : team.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of your team.</p>
            <Link className="btn secondary small" href="/recruiter/manager/team">Go to the first page</Link>
          </>
        ) : (
          <RecruiterTeamTable page={team} />
        )}
      </div>
    </PortalShell>
  );
}

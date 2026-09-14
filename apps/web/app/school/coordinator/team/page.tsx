import PortalShell from "@/components/PortalShell";
import SchoolTeamPanel from "@/components/SchoolTeamPanel";
import { serverApi } from "@/lib/api";
import type { User } from "@/lib/types";

type TeamPayload = {
  accounts: { id: string; name: string; email: string; role: string }[];
  pending_invites: { id: string; role: string; email: string; full_name: string; expires_at: string }[];
};

// SCH-003 (DEC-SCOPE-012): School Coordinator has no dashboard yet (SCH-001 is a
// separate, not-yet-built Feature ID) -- Team is this role's only screen today, so it
// stands alone (own single-item nav via PortalShell directly) rather than joining the
// shared PORTAL_NAV/[section] dispatcher every other role already has.
export default async function SchoolCoordinatorTeamPage() {
  let user: User;
  let team: TeamPayload;
  try {
    [user, team] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<TeamPayload>("/api/v1/school/team")]);
  } catch (e) {
    return (
      <div className="section">
        <div className="container card">
          <h1>Access unavailable</h1>
          <p>{e instanceof Error ? e.message : "Unable to load this workspace"}</p>
          <a className="btn" href="/overseas/login">Return to login</a>
        </div>
      </div>
    );
  }
  return (
    <PortalShell nav={[{ label: "Team", href: "/school/coordinator/team" }]} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolTeamPanel accounts={team.accounts} pendingInvites={team.pending_invites} />
    </PortalShell>
  );
}

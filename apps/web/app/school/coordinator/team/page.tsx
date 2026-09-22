import PortalShell from "@/components/PortalShell";
import SchoolTeamPanel from "@/components/SchoolTeamPanel";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessUnavailable } from "@/components/AccessUnavailable";

type TeamPayload = {
  accounts: { id: string; name: string; email: string; role: string; active: boolean }[];
  pending_invites: { id: string; role: string; email: string; full_name: string; expires_at: string }[];
};

// SCH-003 (DEC-SCOPE-012). Part of the Coordinator's own SCHOOL_NAV (lib/navigation.ts),
// not the shared PORTAL_NAV/[section] dispatcher -- see that file's own note on why.
export default async function SchoolCoordinatorTeamPage() {
  let user: User;
  let team: TeamPayload;
  try {
    [user, team] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<TeamPayload>("/api/v1/school/team")]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolTeamPanel accounts={team.accounts} pendingInvites={team.pending_invites} />
    </PortalShell>
  );
}

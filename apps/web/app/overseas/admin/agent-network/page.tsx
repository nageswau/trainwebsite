import AgentNetworkPanel from "@/components/AgentNetworkPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";

// AGN-022 (DEC-SCOPE-063): the agent network for Overseas and Super Admins, readable by both like the API. The panel owns the page
// heading; it is full width (not in .action-grid) because its table needs the room. The unauthenticated redirect is the middleware's.
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function AgentNetworkPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e);
  }
  if (!ADMIN_ROLES.includes(user.role)) return accessDenied(user, "Overseas Administrator role required");
  return (
    <PortalShell nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" userName={user.full_name}>
      <div className="portal-content">
        <AgentNetworkPanel />
      </div>
    </PortalShell>
  );
}

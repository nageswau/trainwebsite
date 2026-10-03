import { notFound } from "next/navigation";

import AgentOrgDetailPanel from "@/components/AgentOrgDetailPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { isUuid } from "@/lib/agentNetwork";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";

// AGN-022 (DEC-SCOPE-063): one agency in the agent network. A path segment that is not a UUID is not-found before anything is
// fetched (AC11). Readable by Overseas and Super Admins; only Overseas Admin may suspend / reinstate (N3), so `canAct` follows the role.
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function AgentOrgPage({ params }: { params: Promise<{ orgId: string }> }) {
  const { orgId } = await params;
  if (!isUuid(orgId)) notFound();
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
        <AgentOrgDetailPanel orgId={orgId} canAct={user.role === "overseas_admin"} />
      </div>
    </PortalShell>
  );
}

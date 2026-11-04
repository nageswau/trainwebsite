import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterRoutingPanel from "@/components/RecruiterRoutingPanel";
import { serverApi } from "@/lib/api";
import { RECRUITER_MANAGER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { PLACEMENT_MANAGER_LABEL } from "@/lib/recruiter";
import type { User } from "@/lib/types";

// hrc-024 (DEC-SCOPE-393 R11): candidate routing -- the placement manager's (and super_admin's). The API enforces who may read and write.
export default async function RecruiterManagerRoutingPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (!["placement_manager", "super_admin"].includes(user.role)) return accessDenied(user, "Placement manager role required");
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : RECRUITER_MANAGER_NAV} roleLabel={superAdmin ? "Super Administrator" : PLACEMENT_MANAGER_LABEL} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Recruiter CRM</div>
            <h2>Candidate routing</h2>
          </div>
        </div>
        <RecruiterRoutingPanel />
      </div>
    </PortalShell>
  );
}

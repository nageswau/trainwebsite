import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterScreeningBank from "@/components/RecruiterScreeningBank";
import { serverApi } from "@/lib/api";
import { RECRUITER_MANAGER_NAV, RECRUITER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { PLACEMENT_MANAGER_LABEL, RECRUITER_ROLE_LABEL } from "@/lib/recruiter";
import type { User } from "@/lib/types";

// pob-020: the shell behind /recruiter/screening-bank (recruiters) and /recruiter/manager/screening-bank (managers, super_admin). The role
// check only spares other roles a screen that can only fail -- the API enforces who may read and write.
export default async function RecruiterScreeningBankPage({ manager }: { manager: boolean }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, manager ? "/admin/login" : "/it/login");
  }
  const allowed = manager ? ["placement_manager", "super_admin"].includes(user.role) : user.role === "placement_team";
  if (!allowed) return accessDenied(user, manager ? "Placement manager role required" : "Recruiter role required");
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : manager ? RECRUITER_MANAGER_NAV : RECRUITER_NAV} roleLabel={superAdmin ? "Super Administrator" : manager ? PLACEMENT_MANAGER_LABEL : RECRUITER_ROLE_LABEL} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Screening</div>
            <h2>Question bank and templates</h2>
            <p className="muted">The questions recruiters ask, and the templates each requirement&apos;s screening form starts from.</p>
          </div>
        </div>
        <RecruiterScreeningBank />
      </div>
    </PortalShell>
  );
}

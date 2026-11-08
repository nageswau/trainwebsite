import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import EscalationRules from "@/components/EscalationRules";
import IntakeTaskTemplate from "@/components/IntakeTaskTemplate";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { RECRUITER_MANAGER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { PLACEMENT_MANAGER_LABEL } from "@/lib/recruiter";
import type { User } from "@/lib/types";

// pob-027 (DEC-SCOPE-434 I3/I7/I10): the Team Lead's intake automation -- the tasks a new requirement's owner starts with, and the
// escalation rules. The manager's (and super_admin's) screen; the API enforces who may read and write.
export default async function IntakeAutomationPage() {
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
            <h2>Intake automation</h2>
            <p className="muted">
              A new requirement goes to the company&rsquo;s recruiter, who is notified at once. With no active recruiter it waits in the
              Unassigned queue and every Team Lead is notified.
            </p>
          </div>
        </div>
        <IntakeTaskTemplate />
        <EscalationRules />
      </div>
    </PortalShell>
  );
}

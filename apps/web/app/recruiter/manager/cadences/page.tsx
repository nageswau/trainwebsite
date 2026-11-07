import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterCadenceLibrary from "@/components/RecruiterCadenceLibrary";
import { serverApi } from "@/lib/api";
import { RECRUITER_MANAGER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { PLACEMENT_MANAGER_LABEL } from "@/lib/recruiter";
import type { User } from "@/lib/types";

// pob-008 (DEC-SCOPE-423 B5): the Team Lead's outreach cadences. Recruiters pick one on an outreach message on a company page; this screen
// is the manager's (and super_admin's). The API enforces who may read and write.
export default async function RecruiterCadencesPage() {
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
            <h2>Outreach cadences</h2>
            <p className="muted">
              A cadence is a sequence of touches, such as Day 0 email, Day 3 LinkedIn, Day 7 call. A recruiter starts one on an outreach message;
              when the contact has not replied by a step&rsquo;s day, that step appears as a follow-up. A reply or Do Not Contact stops it.
            </p>
          </div>
        </div>
        <RecruiterCadenceLibrary />
      </div>
    </PortalShell>
  );
}

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterManagementPanel from "@/components/RecruiterManagementPanel";
import { ApiError, serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import { companyShell } from "@/lib/recruiterCompanies";
import { MANAGEMENT_URL, managementError, managementParams, managementQuery, type Management } from "@/lib/recruiterManagement";
import { istToday } from "@/lib/telecallerTargets";
import type { User } from "@/lib/types";

const ROLES = ["placement_manager", "super_admin", "it_admin"]; // MG1 (rec-033 PF1)

// rec-035 (EVID-018 §26, DEC-SCOPE-184): "The CEO/Manager should get one view" of the recruiter business. The role check only spares other roles a
// screen that can only fail; the API decides whose figures are in scope (a manager's team + the Unassigned queue; administrators all).
export default async function RecruiterManagementPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = managementParams(await searchParams);
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (!ROLES.includes(user.role)) return accessDenied(user, "Placement manager or administrator role required");
  let data: Management | null = null;
  let error = "";
  try {
    data = await serverApi<Management>(MANAGEMENT_URL + managementQuery(params));
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) return accessUnavailable(e, "/admin/login");
    error = managementError(e);
  }
  const { nav, roleLabel } = user.role === "it_admin" ? { nav: PORTAL_NAV["it/admin"], roleLabel: "IT Administrator" } : companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Management dashboard</div>
            <h2>Recruiter business</h2>
            <p className="muted">
              {user.role === "placement_manager" ? "Your team's" : "Every recruiter's"} companies, requirements and candidates, plus those not yet
              given to a recruiter. Interviews, selections, joinings and top companies count the period; the rest are as of now.
            </p>
          </div>
        </div>
        <RecruiterManagementPanel data={data} error={error} params={params} today={istToday()} />
      </div>
    </PortalShell>
  );
}

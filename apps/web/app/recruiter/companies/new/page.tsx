import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterCompanyCreate from "@/components/RecruiterCompanyCreate";
import { serverApi } from "@/lib/api";
import { COMPANIES_URL, companyShell, CREATOR_ROLES, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";

// rec-003 (EVID-018 quick action "+ Add Company"): a recruiter's new company is their own; a manager may hand it to a recruiter.
export default async function RecruiterCompanyNewPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${COMPANIES_URL}?limit=1`)]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  if (!CREATOR_ROLES.includes(user.role)) return accessDenied(user, "Your role cannot add companies");
  const { nav, roleLabel } = companyShell(user.role);
  const recruiter = user.role === "placement_team";
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Companies</div>
            <h2>Add company</h2>
            <p className="muted">{recruiter ? "It will be assigned to you." : "Choose a recruiter, or leave it in the unassigned queue."}</p>
          </div>
        </div>
        <div className="action-card wide">
          <RecruiterCompanyCreate canChooseRecruiter={!recruiter} />
        </div>
      </div>
    </PortalShell>
  );
}

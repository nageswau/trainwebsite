import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterRequirementCreate from "@/components/RecruiterRequirementCreate";
import { ApiError, serverApi } from "@/lib/api";
import type { PickOption } from "@/lib/lookups";
import { type Company, COMPANIES_URL, companyShell, CREATOR_ROLES, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { REQUIREMENTS_URL } from "@/lib/recruiterRequirements";
import type { User } from "@/lib/types";

// rec-007 (EVID-018 quick action "+ Add Job Requirement"): from a company page the company is fixed (`?company_id=`); otherwise the
// user picks one of theirs. A recruiter's requirement is their own; a manager may hand it to a recruiter.
export default async function RecruiterRequirementNewPage({ searchParams }: { searchParams: Promise<{ company_id?: string }> }) {
  const companyId = (await searchParams).company_id;
  let user: User;
  let company: PickOption | null = null;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${REQUIREMENTS_URL}?limit=1`)]);
    if (companyId) {
      try {
        const read = await serverApi<{ company: Company }>(`${COMPANIES_URL}/${encodeURIComponent(companyId)}`);
        if (!read.company.archived) company = { id: read.company.id, label: read.company.name, detail: read.company.code };
      } catch (e) {
        if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) throw e; // an unknown company: pick one instead
      }
    }
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  if (!CREATOR_ROLES.includes(user.role)) return accessDenied(user, "Your role cannot add job requirements");
  const { nav, roleLabel } = companyShell(user.role);
  const recruiter = user.role === "placement_team";
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Job requirements</div>
            <h2>Add job requirement</h2>
            <p className="muted">
              {recruiter ? "It will be assigned to you. It starts as New." : "Choose a recruiter, or leave it with the company's recruiter. It starts as New."}
            </p>
          </div>
        </div>
        <div className="action-card wide">
          <RecruiterRequirementCreate company={company} canChooseRecruiter={!recruiter} />
        </div>
      </div>
    </PortalShell>
  );
}

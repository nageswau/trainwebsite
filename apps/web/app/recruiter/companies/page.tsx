import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterCompaniesPanel from "@/components/RecruiterCompaniesPanel";
import { serverApi } from "@/lib/api";
import { COMPANIES_URL, companyShell, CREATOR_ROLES, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";

// rec-003 (spec §6): the company master list. The API is the gate: a role without access (hr_team, it_admin, employer...) or a
// recruiter without a profile gets its 403 message here, from the probe read alongside the session.
export default async function RecruiterCompaniesPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${COMPANIES_URL}?limit=1`)]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  const manager = user.role === "placement_manager" || user.role === "super_admin";
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Companies</div>
            <h2>{manager ? "Your team's companies" : user.role === "bdm" ? "Companies you are linked to" : "Your companies"}</h2>
            <p className="muted">
              {manager ? "Companies your recruiters own, and new ones waiting for a recruiter." : "Each recruiter lead is a company. Its code is assigned when you save it."}
            </p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading companies…</p>}>
          <RecruiterCompaniesPanel canCreate={CREATOR_ROLES.includes(user.role)} isManager={manager} />
        </Suspense>
      </div>
    </PortalShell>
  );
}

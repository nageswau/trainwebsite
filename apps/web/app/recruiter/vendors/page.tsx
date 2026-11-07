import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterCompaniesPanel from "@/components/RecruiterCompaniesPanel";
import { serverApi } from "@/lib/api";
import { COMPANIES_URL, companyShell, CREATOR_ROLES, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";

// pob-010 (DEC-SCOPE-420 V1/V10): the vendor list -- the company list with `relationship=vendor`, in the same scope. The API is the gate.
export default async function RecruiterVendorsPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${COMPANIES_URL}?limit=1&relationship=vendor`)]);
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
            <div className="eyebrow">Vendors</div>
            <h2>Vendors and staffing partners</h2>
            <p className="muted">Partners you work with, and how far each has come through onboarding.</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading vendors…</p>}>
          <RecruiterCompaniesPanel canCreate={CREATOR_ROLES.includes(user.role)} isManager={manager} vendors />
        </Suspense>
      </div>
    </PortalShell>
  );
}

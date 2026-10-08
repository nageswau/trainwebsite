import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterCompaniesPanel from "@/components/RecruiterCompaniesPanel";
import { serverApi } from "@/lib/api";
import { COMPANIES_URL, companyShell, CREATOR_ROLES, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";

// QA-03: each role's heading says what its scope is (super admin sees every company).
const HEADING: Record<string, string> = { super_admin: "All companies", placement_manager: "Your team's companies", bdm: "Companies you are linked to" };
const INTRO: Record<string, string> = {
  super_admin: "Every recruiter's companies, and new ones waiting for a recruiter.",
  placement_manager: "Companies your recruiters own, and new ones waiting for a recruiter.",
  bdm: "Recruiter companies where you are the Assigned BDM. You can view them; the recruiter keeps them up to date.",
};

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
            <h2>{HEADING[user.role] ?? "Your companies"}</h2>
            <p className="muted">
              {INTRO[user.role] ?? "Each recruiter lead is a company. Its code is assigned when you save it."}
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

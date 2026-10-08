import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterRequirementsPanel from "@/components/RecruiterRequirementsPanel";
import { serverApi } from "@/lib/api";
import { companyShell, CREATOR_ROLES, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { REQUIREMENTS_URL } from "@/lib/recruiterRequirements";
import type { User } from "@/lib/types";

const HEADING: Record<string, string> = { super_admin: "All job requirements", placement_manager: "Your team's job requirements", bdm: "Job requirements of your companies" };
const INTRO: Record<string, string> = {
  super_admin: "Every company's requirements, from every recruiter.",
  placement_manager: "Requirements your recruiters own, and new ones waiting for a recruiter.",
  bdm: "Requirements of the recruiter companies where you are the Assigned BDM. You can view them; the recruiter keeps them up to date.",
};

// rec-007 (spec §6): the requirement list. The API is the gate: a role without access (hr_team, it_admin, employer...) gets its 403
// message here, from the probe read alongside the session.
export default async function RecruiterRequirementsPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${REQUIREMENTS_URL}?limit=1`)]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Job requirements</div>
            <h2>{HEADING[user.role] ?? "Your job requirements"}</h2>
            <p className="muted">{INTRO[user.role] ?? "Requirements you own, and those of your companies. Each gets its code when you save it."}</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading job requirements…</p>}>
          <RecruiterRequirementsPanel canCreate={CREATOR_ROLES.includes(user.role)} isManager={user.role === "placement_manager" || user.role === "super_admin"} />
        </Suspense>
      </div>
    </PortalShell>
  );
}

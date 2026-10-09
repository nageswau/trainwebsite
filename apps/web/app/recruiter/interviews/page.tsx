import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterInterviewsPanel from "@/components/RecruiterInterviewsPanel";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { INTERVIEWS_URL } from "@/lib/recruiterInterviews";
import type { User } from "@/lib/types";

const INTRO: Record<string, string> = {
  placement_team: "Your requirements' interviews. Schedule one from a candidate on a requirement; Awaiting update lists interviews whose time has passed.",
  placement_manager: "Your team's interviews (read only).",
};

// rec-020 (spec §4): the interviews list (IV12). The API is the gate: a role without access (hr_team, it_admin, employer...) or a
// recruiter without a profile gets its 403 message here, from the probe read alongside the session.
export default async function RecruiterInterviewsPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${INTERVIEWS_URL}?limit=1`)]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Interviews</div>
            <h2>Interviews</h2>
            <p className="muted">{INTRO[user.role] ?? "Interviews on the requirements you can see."}</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading interviews…</p>}>
          <RecruiterInterviewsPanel />
        </Suspense>
      </div>
    </PortalShell>
  );
}

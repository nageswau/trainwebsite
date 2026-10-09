import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterJoiningsPanel from "@/components/RecruiterJoiningsPanel";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { JOININGS_URL } from "@/lib/recruiterOffers";
import type { User } from "@/lib/types";

const INTRO: Record<string, string> = {
  placement_team: "Accepted offers waiting to join, and the joinings closed. Update a joining from the candidate's offer on the requirement.",
  placement_manager: "Your team's joinings (read only).",
};

// rec-023 (spec §4): the joinings list. The API is the gate: a role without access (hr_team, it_admin, employer...) or a recruiter
// without a profile gets its 403 message here, from the probe read alongside the session.
export default async function RecruiterJoiningsPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${JOININGS_URL}?limit=1`)]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Joinings</div>
            <h2>Joinings</h2>
            <p className="muted">{INTRO[user.role] ?? "Joinings on the requirements you can see."}</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading joinings…</p>}>
          <RecruiterJoiningsPanel />
        </Suspense>
      </div>
    </PortalShell>
  );
}

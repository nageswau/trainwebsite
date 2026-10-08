import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterMeetingsPanel from "@/components/RecruiterMeetingsPanel";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { MEETINGS_URL } from "@/lib/recruiterMeetings";
import type { User } from "@/lib/types";

const INTRO: Record<string, string> = {
  placement_team: "Your companies' meetings. Awaiting outcome lists meetings that have started without an outcome yet.",
  placement_manager: "Your team's meetings (read only).",
};

// rec-028 (spec §4): the meetings list (MT10). The API is the gate: a role without access (hr_team, it_admin, employer...) or a
// recruiter without a profile gets its 403 message here, from the probe read alongside the session.
export default async function RecruiterMeetingsPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${MEETINGS_URL}?limit=1`)]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Meetings</div>
            <h2>Meetings</h2>
            <p className="muted">{INTRO[user.role] ?? "Meetings with the companies you can see."}</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading meetings…</p>}>
          <RecruiterMeetingsPanel />
        </Suspense>
      </div>
    </PortalShell>
  );
}

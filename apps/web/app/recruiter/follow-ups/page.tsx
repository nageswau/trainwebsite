import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterFollowUpsPanel from "@/components/RecruiterFollowUpsPanel";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { FOLLOW_UPS_URL } from "@/lib/recruiterFollowUps";
import type { User } from "@/lib/types";

const INTRO: Record<string, string> = {
  placement_team: "Your companies' follow-ups. Today lists everything due today and everything overdue.",
  placement_manager: "Your team's follow-ups (read only). Today lists everything due today and everything overdue.",
};

// rec-024 (spec §4): the daily follow-up list. The API is the gate: a role without access (hr_team, it_admin, employer...) or a
// recruiter without a profile gets its 403 message here, from the probe read alongside the session.
export default async function RecruiterFollowUpsPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${FOLLOW_UPS_URL}?limit=1`)]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Follow-ups</div>
            <h2>Follow-ups</h2>
            <p className="muted">{INTRO[user.role] ?? "Follow-ups on the companies you can see."}</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading follow-ups…</p>}>
          <RecruiterFollowUpsPanel />
        </Suspense>
      </div>
    </PortalShell>
  );
}

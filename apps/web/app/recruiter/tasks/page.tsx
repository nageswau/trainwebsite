import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterMyTasksPanel from "@/components/RecruiterMyTasksPanel";
import { serverApi } from "@/lib/api";
import { TASKS_URL } from "@/lib/recruiterCandidateTasks";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import type { User } from "@/lib/types";

// hrc-016 (T8): the candidate tasks assigned to the signed-in recruiter or manager. The API is the gate: a role that cannot be given a
// task (hr_team, it_admin, employer...) gets its 403 message here, from the probe read alongside the session.
export default async function RecruiterTasksPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${TASKS_URL}?limit=1`)]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Candidate tasks</div>
            <h2>My tasks</h2>
            <p className="muted">Candidate tasks assigned to you. Today lists everything due today and everything overdue.</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading tasks…</p>}>
          <RecruiterMyTasksPanel />
        </Suspense>
      </div>
    </PortalShell>
  );
}

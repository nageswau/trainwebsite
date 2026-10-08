import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterProfileCard from "@/components/RecruiterProfileCard";
import { serverApi } from "@/lib/api";
import { RECRUITER_NAV } from "@/lib/navigation";
import { RECRUITER_ROLE_LABEL, type RecruiterMe } from "@/lib/recruiter";

// rec-001 (AC3): the recruiter landing page -- a shell that rec-032 fills in. The API is the gate: any other role (hr_team included,
// Q-28), or a recruiter without a profile, gets its 403 message here.
export default async function RecruiterDashboardPage() {
  let me: RecruiterMe;
  try {
    me = await serverApi<RecruiterMe>("/api/v1/recruiter/me");
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  return (
    <PortalShell nav={RECRUITER_NAV} roleLabel={RECRUITER_ROLE_LABEL} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Recruiter dashboard</div>
            <h2>Welcome, {me.full_name}</h2>
            <p className="muted">Your companies, requirements and candidates will appear here. Until then, the placement screens are in the menu — start with <Link href="/it/placement/candidates">Candidates</Link>.</p>
          </div>
        </div>
        <RecruiterProfileCard me={me} />
      </div>
    </PortalShell>
  );
}

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterColleges from "@/components/RecruiterColleges";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { COLLEGES_URL } from "@/lib/recruiterColleges";
import type { User } from "@/lib/types";

const INTRO: Record<string, string> = {
  placement_team: "Colleges and universities from the BDM CRM. Keep their courses, batches, placement calendar and TPO interactions here.",
  placement_manager: "Colleges and universities from the BDM CRM (read only).",
};

// pob-013 (DEC-SCOPE-410): the colleges list. The API is the gate: a role without access (hr_team, placement_officer, employer...) or a
// recruiter without a profile gets its 403 message here, from the probe read alongside the session (the rec-029 pattern).
export default async function RecruiterCollegesPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${COLLEGES_URL}?limit=1`)]);
  } catch (e) {
    return accessUnavailable(e, RECRUITER_SIGN_IN);
  }
  const { nav, roleLabel } = companyShell(user.role);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Recruitment</div>
            <h2>Colleges</h2>
            <p className="muted">{INTRO[user.role] ?? "Colleges and universities you can see."}</p>
          </div>
        </div>
        <RecruiterColleges />
      </div>
    </PortalShell>
  );
}

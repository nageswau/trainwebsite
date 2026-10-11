import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterDrives from "@/components/RecruiterDrives";
import { serverApi } from "@/lib/api";
import { companyShell, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { DRIVES_URL } from "@/lib/recruiterDrives";
import type { User } from "@/lib/types";

const INTRO: Record<string, string> = {
  placement_team: "Recruit from a college for your companies' requirements. Candidates added through a drive feed its funnel.",
  placement_manager: "Your team's campus drives (read only).",
};

// rec-029 (DEC-SCOPE-176): the campus drives list. The API is the gate: a role without access (hr_team, it_admin, employer...) or a
// recruiter without a profile gets its 403 message here, from the probe read alongside the session (the rec-028 pattern).
export default async function RecruiterDrivesPage() {
  let user: User;
  try {
    [user] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi(`${DRIVES_URL}?limit=1`)]);
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
            <h2>Campus Drives</h2>
            <p className="muted">{INTRO[user.role] ?? "Campus drives of the companies you can see."}</p>
          </div>
        </div>
        <RecruiterDrives />
      </div>
    </PortalShell>
  );
}

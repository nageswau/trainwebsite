import { accessUnavailable } from "@/components/AccessUnavailable";
import CandidatePrivacyPanel from "@/components/CandidatePrivacyPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { CANDIDATE_NAV, PRIVACY_URL, type PrivacyState } from "@/lib/candidatePortal";
import type { User } from "@/lib/types";

// hrc-022 (DEC-SCOPE-385 C12): the candidate's consent and its history.
export default async function CandidatePrivacyPage() {
  let user: User;
  let privacy: PrivacyState;
  try {
    [user, privacy] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<PrivacyState>(PRIVACY_URL)]);
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  return (
    <PortalShell nav={CANDIDATE_NAV} roleLabel="Candidate" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Candidate portal</div>
            <h2>Privacy</h2>
            <p className="muted">What you agreed to, and whether recruiters can find you in the candidate pool.</p>
          </div>
        </div>
        <CandidatePrivacyPanel initial={privacy} />
      </div>
    </PortalShell>
  );
}

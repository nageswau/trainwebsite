import { accessUnavailable } from "@/components/AccessUnavailable";
import CandidatePrivacyPanel from "@/components/CandidatePrivacyPanel";
import ContactDetailsCard from "@/components/ContactDetailsCard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { CANDIDATE_NAV, CANDIDATE_PORTAL_HOME, type CandidateProfile, PRIVACY_URL, PROFILE_URL, type PrivacyState } from "@/lib/candidatePortal";
import type { User } from "@/lib/types";

// hrc-022 (DEC-SCOPE-386 C12): the candidate's consent and its history.
export default async function CandidatePrivacyPage() {
  let user: User;
  let privacy: PrivacyState;
  let profile: CandidateProfile;
  try {
    [user, privacy, profile] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<PrivacyState>(PRIVACY_URL), serverApi<CandidateProfile>(PROFILE_URL)]);
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
        {/* hrc-031 (DEC-SCOPE-412 P10) */}
        <div style={{ marginBottom: 16 }}>
          <ContactDetailsCard email={profile.email} verified={profile.email_verified} pendingEmail={profile.pending_email} mobile={profile.mobile} changeHref={CANDIDATE_PORTAL_HOME} />
        </div>
        <CandidatePrivacyPanel initial={privacy} />
      </div>
    </PortalShell>
  );
}

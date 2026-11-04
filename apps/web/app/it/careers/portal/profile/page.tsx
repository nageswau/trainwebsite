import { accessUnavailable } from "@/components/AccessUnavailable";
import CandidateProfileForm from "@/components/CandidateProfileForm";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { CANDIDATE_NAV, PROFILE_URL, type CandidateProfile } from "@/lib/candidatePortal";
import type { User } from "@/lib/types";

// hrc-022 (DEC-SCOPE-384 C10): the candidate's own profile. The API decides who reads it (a candidate; anyone else 403, shown as the
// access card) and whose record it is (always the caller's own).
export default async function CandidateProfilePage() {
  let user: User;
  let profile: CandidateProfile;
  try {
    [user, profile] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<CandidateProfile>(PROFILE_URL)]);
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  return (
    <PortalShell nav={CANDIDATE_NAV} roleLabel="Candidate" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Candidate portal</div>
            <h2>My profile</h2>
            <p className="muted">Keep your details current so recruiters can match you to the right openings.</p>
          </div>
        </div>
        <CandidateProfileForm initial={profile} />
      </div>
    </PortalShell>
  );
}

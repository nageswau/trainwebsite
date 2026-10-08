import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterProfileCard from "@/components/RecruiterProfileCard";
import TelecallerPhoneForm from "@/components/TelecallerPhoneForm";
import { serverApi } from "@/lib/api";
import { RECRUITER_NAV } from "@/lib/navigation";
import { RECRUITER_PROFILE_URL, RECRUITER_ROLE_LABEL, type RecruiterMe } from "@/lib/recruiter";

// rec-001: the recruiter's own profile; only the mobile is editable here (the tel-001 TL3 rule).
export default async function RecruiterProfilePage() {
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
            <div className="eyebrow">Profile</div>
            <h2>My profile</h2>
            <p className="muted">You can update your mobile number. Contact your administrator to change anything else.</p>
          </div>
        </div>
        <RecruiterProfileCard me={me} />
        <TelecallerPhoneForm phone={me.phone} url={RECRUITER_PROFILE_URL} idPrefix="recruiter" />
      </div>
    </PortalShell>
  );
}

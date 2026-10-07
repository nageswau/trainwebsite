import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import TelecallerPhoneForm from "@/components/TelecallerPhoneForm";
import TelecallerProfileCard from "@/components/TelecallerProfileCard";
import { serverApi } from "@/lib/api";
import { TELECALLER_SIGN_IN } from "@/lib/navigation";
import { telecallerNav } from "@/lib/telecallerNav";
import { teamRoleLabel, type TelecallerMe } from "@/lib/telecaller";

// tel-001: the telecaller's own profile; only the mobile is editable here (TL3).
export default async function TelecallerProfilePage() {
  let me: TelecallerMe;
  try {
    me = await serverApi<TelecallerMe>("/api/v1/telecaller/me");
  } catch (e) {
    return accessUnavailable(e, TELECALLER_SIGN_IN);
  }
  return (
    <PortalShell nav={await telecallerNav()} roleLabel={teamRoleLabel(me.telecaller_profile.team)} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Profile</div>
            <h2>My profile</h2>
            <p className="muted">You can update your mobile number. Contact your administrator to change anything else.</p>
          </div>
        </div>
        <TelecallerProfileCard me={me} />
        <TelecallerPhoneForm phone={me.phone} />
      </div>
    </PortalShell>
  );
}

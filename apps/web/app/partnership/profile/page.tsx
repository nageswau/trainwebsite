import { accessUnavailable } from "@/components/AccessUnavailable";
import PartnershipProfileCard from "@/components/PartnershipProfileCard";
import PortalShell from "@/components/PortalShell";
import TelecallerPhoneForm from "@/components/TelecallerPhoneForm";
import { serverApi } from "@/lib/api";
import { PARTNERSHIP_NAV } from "@/lib/navigation";
import { ME_URL, PROFILE_URL, ROLE_LABEL, type PartnershipMe } from "@/lib/partnership";

// upc-001: the manager's own profile; only the mobile is editable here (PU3).
export default async function PartnershipProfilePage() {
  let me: PartnershipMe;
  try {
    me = await serverApi<PartnershipMe>(ME_URL);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  return (
    <PortalShell nav={PARTNERSHIP_NAV} roleLabel={ROLE_LABEL.manager} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Profile</div>
            <h2>My profile</h2>
            <p className="muted">You can update your mobile number. Contact your administrator to change anything else.</p>
          </div>
        </div>
        <PartnershipProfileCard me={me} />
        <TelecallerPhoneForm phone={me.phone} url={PROFILE_URL} />
      </div>
    </PortalShell>
  );
}

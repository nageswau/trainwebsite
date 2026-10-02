import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmProfileCard from "@/components/BdmProfileCard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { BDM_NAV, BDM_SIGN_IN } from "@/lib/navigation";

// bdm-001: the BDM's own §1 profile, read-only (admins edit it).
export default async function BdmProfilePage() {
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  return (
    <PortalShell nav={BDM_NAV} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Profile</div>
            <h2>My profile</h2>
            <p className="muted">Your details as recorded by your administrator. Contact them to change anything.</p>
          </div>
        </div>
        <BdmProfileCard me={me} />
      </div>
    </PortalShell>
  );
}

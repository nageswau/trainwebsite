import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmProfileCard from "@/components/BdmProfileCard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { BDM_NAV, BDM_SIGN_IN } from "@/lib/navigation";

// bdm-001 (AC05, B2): the BDM landing page -- a minimal shell; bdm-014 fills My Day. The API is the gate: any other role, or a BDM
// without a profile, gets its 403 message here with a link home.
export default async function BdmMyDayPage() {
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
            <div className="eyebrow">My Day</div>
            <h2>Welcome, {me.full_name}</h2>
            <p className="muted">Your appointments, travel and follow-ups will appear here.</p>
          </div>
        </div>
        <BdmProfileCard me={me} />
      </div>
    </PortalShell>
  );
}

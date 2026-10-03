import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmOrganizationsPanel from "@/components/BdmOrganizationsPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { BDM_NAV, BDM_SIGN_IN } from "@/lib/navigation";

// bdm-002: every organization of the BDM's module (Q-02). The API is the gate.
export default async function BdmOrganizationsPage() {
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
            <div className="eyebrow">Organizations</div>
            <h2>{BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} organizations</h2>
            <p className="muted">Every organization in your module. You can edit the ones assigned to you.</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading organizations…</p>}>
          <BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />
        </Suspense>
      </div>
    </PortalShell>
  );
}

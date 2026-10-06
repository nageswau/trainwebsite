import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmTasksPanel from "@/components/BdmTasksPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { bdmNav } from "@/lib/bdmNav";
import { BDM_SIGN_IN } from "@/lib/navigation";

// bdm-008: the BDM's own follow-ups and tasks. The API is the gate.
export default async function BdmFollowUpsPage() {
  const nav = bdmNav(); // the unread badge, read alongside the page's own data (never rejects)
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Follow-ups</div>
            <h2>Your follow-ups and tasks</h2>
            <p className="muted">Dates are India time (IST).</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading follow-ups…</p>}>
          <BdmTasksPanel isBdm />
        </Suspense>
      </div>
    </PortalShell>
  );
}

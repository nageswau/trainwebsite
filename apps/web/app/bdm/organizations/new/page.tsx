import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmOrganizationCreate from "@/components/BdmOrganizationCreate";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { bdmNav } from "@/lib/bdmNav";
import { BDM_SIGN_IN } from "@/lib/navigation";

export default async function BdmOrganizationNewPage() {
  const nav = bdmNav(); // bdm-010 QA10-01: the unread badge, read alongside the page's own data (never rejects)
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
            <div className="eyebrow">Organizations</div>
            <h2>Add organization</h2>
            <p className="muted">It will belong to the {BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} module and be assigned to you.</p>
          </div>
        </div>
        <div className="action-card wide"><BdmOrganizationCreate /></div>
      </div>
    </PortalShell>
  );
}

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmMousPanel from "@/components/BdmMousPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe, pageOffset } from "@/lib/bdm";
import type { MouStatus } from "@/lib/bdmMous";
import { readMous } from "@/lib/bdmMousServer";
import { bdmNav } from "@/lib/bdmNav";
import { BDM_SIGN_IN } from "@/lib/navigation";

const PATH = "/bdm/mous";

// bdm-005 (spec §8): the module's MoUs (the BDM read scope, as the organizations), filtered by derived status in the address.
export default async function BdmMousPage({ searchParams }: { searchParams: Promise<{ status?: string; offset?: string }> }) {
  const nav = bdmNav();
  const sp = await searchParams;
  const status = (sp.status || undefined) as MouStatus | undefined; // an unknown value is the API's 422, shown as "invalid"
  let me: BdmMe;
  let page: Awaited<ReturnType<typeof readMous>>;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
    page = await readMous({ status, offset: pageOffset(sp.offset) });
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  const type = BDM_TYPE_LABEL[me.bdm_profile.bdm_type];
  return (
    <PortalShell nav={await nav} roleLabel={`${type} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">MoUs</div>
            <h2>{type} MoUs</h2>
            <p className="muted">Each organization&apos;s current MoU. A Signed or Active MoU past its valid-until date reads Expired.</p>
          </div>
        </div>
        {page === "invalid" ? (
          <div className="action-card">
            <p>That filter isn&apos;t valid.</p>
            <p><a href={PATH}>Show all MoUs</a></p>
          </div>
        ) : (
          <BdmMousPanel page={page} status={status ?? null} path={PATH} orgBasePath="/bdm/organizations" />
        )}
      </div>
    </PortalShell>
  );
}

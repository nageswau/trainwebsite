import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmOrganizationDetail from "@/components/BdmOrganizationDetail";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { firstActivityPage } from "@/lib/bdmActivitiesServer";
import type { Organization } from "@/lib/bdmOrganizations";
import { bdmNav } from "@/lib/bdmNav";
import { firstStageHistory } from "@/lib/bdmPipelineServer";
import { BDM_SIGN_IN } from "@/lib/navigation";

// bdm-002: one organization. A 404 (unknown or outside the BDM's module) is a plain "not found" -- it never says which.
export default async function BdmOrganizationPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ created?: string }> }) {
  const nav = bdmNav(); // bdm-010 QA10-01: the unread badge, read alongside the page's own data (never rejects)
  const { id } = await params;
  const created = (await searchParams).created === "1";
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  const timeline = firstActivityPage(id); // bdm-009: the activity section's first page, read alongside the organization
  const stages = firstStageHistory(id); // bdm-004: the stage history's first page, read alongside the organization
  let organization: Organization | null = null;
  try {
    organization = (await serverApi<{ organization: Organization }>(`/api/v1/bdm/organizations/${encodeURIComponent(id)}`)).organization;
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) return accessUnavailable(e, BDM_SIGN_IN);
  }
  const activities = organization ? await timeline : null;
  const stageHistory = organization ? await stages : null;
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        {organization ? (
          <BdmOrganizationDetail initial={organization} basePath="/bdm/organizations" created={created} activities={activities} stageHistory={stageHistory} />
        ) : (
          <div className="action-card">
            <h2>Organization not found</h2>
            <p><Link href="/bdm/organizations">Back to organizations</Link></p>
          </div>
        )}
      </div>
    </PortalShell>
  );
}

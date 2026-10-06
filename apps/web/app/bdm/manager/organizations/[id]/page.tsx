import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmOrganizationDetail from "@/components/BdmOrganizationDetail";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { firstActivityPage } from "@/lib/bdmActivitiesServer";
import { firstLeadPage } from "@/lib/bdmLeadsServer";
import type { Organization } from "@/lib/bdmOrganizations";
import { bdmManagerNav } from "@/lib/bdmNav";
import { firstMou } from "@/lib/bdmMousServer";
import { firstStageHistory } from "@/lib/bdmPipelineServer";
import { firstTaskPage } from "@/lib/bdmTasksServer";
import type { User } from "@/lib/types";

// bdm-002 (C2, C14): one of the team's organizations for a manager (super_admin: any). A 404 (unknown, or not assigned to this
// manager's team) is a plain "not found" -- it never says which.
export default async function BdmManagerOrganizationPage({ params }: { params: Promise<{ id: string }> }) {
  const nav = bdmManagerNav(); // bdm-010 QA10-01: the unread badge, read alongside the page's own data (never rejects)
  const { id } = await params;
  const timeline = firstActivityPage(id); // bdm-009: the activity section's first page, read alongside the organization
  const leadPage = firstLeadPage(id); // bdm-017: the leads section's first page, likewise
  const stages = firstStageHistory(id); // bdm-004: the stage history's first page, read alongside the organization
  const mouCard = firstMou(id); // bdm-005: the MoU card, likewise (never rejects)
  const taskPage = firstTaskPage(id); // bdm-008: the open follow-ups, likewise
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
  let organization: Organization | null = null;
  try {
    organization = (await serverApi<{ organization: Organization }>(`/api/v1/bdm/organizations/${encodeURIComponent(id)}`)).organization;
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) return accessUnavailable(e, "/admin/login");
  }
  const [activities, leads, stageHistory, tasks, mou] = organization ? await Promise.all([timeline, leadPage, stages, taskPage, mouCard]) : [null, null, null, null, null];
  return (
    <PortalShell nav={await nav} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        {organization ? (
          <BdmOrganizationDetail initial={organization} basePath="/bdm/manager/organizations" activities={activities} leads={leads} stageHistory={stageHistory} tasks={tasks} mou={mou} />
        ) : (
          <div className="action-card">
            <h2>Organization not found</h2>
            <p>
              <Link href="/bdm/manager/organizations">Back to organizations</Link>
            </p>
          </div>
        )}
      </div>
    </PortalShell>
  );
}

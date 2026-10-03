import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmOrganizationDetail from "@/components/BdmOrganizationDetail";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { type Activity, orgActivitiesUrl } from "@/lib/bdmActivities";
import type { Organization } from "@/lib/bdmOrganizations";
import { bdmManagerNav } from "@/lib/bdmNav";
import { isUuid } from "@/lib/bdmTravel";
import type { User } from "@/lib/types";

// bdm-002 (C2, C14): one of the team's organizations for a manager (super_admin: any). A 404 (unknown, or not assigned to this
// manager's team) is a plain "not found" -- it never says which.
export default async function BdmManagerOrganizationPage({ params }: { params: Promise<{ id: string }> }) {
  const nav = bdmManagerNav(); // bdm-010 QA10-01: the unread badge, read alongside the page's own data (never rejects)
  const { id } = await params;
  // bdm-009 (spec §6.2, §12.2 F2): the first timeline page, read alongside the organization (never rejects; null = "Try again").
  const timeline: Promise<Page<Activity> | null> = isUuid(id)
    ? serverApi<Page<Activity>>(orgActivitiesUrl(id)).catch(() => null)
    : Promise.resolve(null);
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
  const activities = organization ? await timeline : null;
  return (
    <PortalShell nav={await nav} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        {organization ? (
          <BdmOrganizationDetail initial={organization} basePath="/bdm/manager/organizations" activities={activities} />
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

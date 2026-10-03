import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmOrganizationsPanel from "@/components/BdmOrganizationsPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { bdmManagerNav } from "@/lib/bdmNav";
import type { User } from "@/lib/types";

// bdm-002 (C2, C14): the organizations assigned to this manager's team (super_admin: all).
export default async function BdmManagerOrganizationsPage() {
  const nav = bdmManagerNav(); // bdm-010 QA10-01: the unread badge, read alongside the page's own data (never rejects)
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
  return (
    <PortalShell nav={await nav} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Organizations</div>
            <h2>Your team&apos;s organizations</h2>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading organizations…</p>}>
          <BdmOrganizationsPanel basePath="/bdm/manager/organizations" isBdm={false} />
        </Suspense>
      </div>
    </PortalShell>
  );
}

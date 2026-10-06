import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmTasksPanel from "@/components/BdmTasksPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { bdmManagerNav } from "@/lib/bdmNav";
import type { User } from "@/lib/types";

// bdm-008 (F4): the follow-ups and tasks of this manager's team (super_admin: all), read-only.
export default async function BdmManagerFollowUpsPage() {
  const nav = bdmManagerNav(); // the unread badge, read alongside the page's own data (never rejects)
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
            <div className="eyebrow">Follow-ups</div>
            <h2>Your team&apos;s follow-ups and tasks</h2>
            <p className="muted">Read-only. Dates are India time (IST).</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading follow-ups…</p>}>
          <BdmTasksPanel isBdm={false} />
        </Suspense>
      </div>
    </PortalShell>
  );
}

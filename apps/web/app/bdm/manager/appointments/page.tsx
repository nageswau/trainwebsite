import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmAppointmentsPanel from "@/components/BdmAppointmentsPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { ALL_TYPES } from "@/lib/bdmAppointments";
import { bdmManagerNav } from "@/lib/bdmNav";
import type { User } from "@/lib/types";

// bdm-006 (A3): the appointments of this manager's team (super_admin: all), read-only.
export default async function BdmManagerAppointmentsPage() {
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
            <div className="eyebrow">Appointments</div>
            <h2>Your team&apos;s appointments</h2>
            <p className="muted">Read-only. Times are India time (IST).</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading appointments…</p>}>
          <BdmAppointmentsPanel basePath="/bdm/manager/appointments" isBdm={false} types={ALL_TYPES} />
        </Suspense>
      </div>
    </PortalShell>
  );
}

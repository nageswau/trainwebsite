import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmAppointmentDetail from "@/components/BdmAppointmentDetail";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { Appointment } from "@/lib/bdmAppointments";
import { BDM_MANAGER_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// bdm-006 (A3): one team appointment, read-only (the API returns all-false permissions for managers and super_admin).
export default async function BdmManagerAppointmentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
  let appointment: Appointment | null = null;
  try {
    appointment = (await serverApi<{ appointment: Appointment }>(`/api/v1/bdm/appointments/${encodeURIComponent(id)}`)).appointment;
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={BDM_MANAGER_NAV} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        {appointment ? (
          <BdmAppointmentDetail initial={appointment} basePath="/bdm/manager/appointments" bdmType={null} />
        ) : (
          <div className="action-card">
            <h2>Appointment not found</h2>
            <p>
              <Link href="/bdm/manager/appointments">Back to appointments</Link>
            </p>
          </div>
        )}
      </div>
    </PortalShell>
  );
}

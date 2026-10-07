import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmAppointmentDetail from "@/components/BdmAppointmentDetail";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { type Appointment, reminderAction } from "@/lib/bdmAppointments";
import { bdmNav } from "@/lib/bdmNav";
import { linkableTrips } from "@/lib/bdmTripChoices";
import { BDM_SIGN_IN } from "@/lib/navigation";

// bdm-006: one appointment. A 404 (unknown or not the BDM's) is a plain "not found" -- it never says which.
// bdm-012: `?action=` is a reminder button (Confirmed / Reschedule / Cancel); the detail opens that action, it never performs it.
export default async function BdmAppointmentPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ created?: string; action?: string }> }) {
  const nav = bdmNav(); // bdm-010 QA10-01: the unread badge, read alongside the page's own data (never rejects)
  const choices = linkableTrips(); // bdm-011: the editor's Trip choice, likewise read alongside (never rejects)
  const { id } = await params;
  const query = await searchParams;
  const created = query.created === "1";
  const action = reminderAction(query.action);
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  let appointment: Appointment | null = null;
  try {
    appointment = (await serverApi<{ appointment: Appointment }>(`/api/v1/bdm/appointments/${encodeURIComponent(id)}`)).appointment;
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) return accessUnavailable(e, BDM_SIGN_IN);
  }
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        {appointment ? (
          <BdmAppointmentDetail initial={appointment} basePath="/bdm/appointments" bdmType={me.bdm_profile.bdm_type} created={created} action={action} {...await choices} />
        ) : (
          <div className="action-card">
            <h2>Appointment not found</h2>
            <p>
              <Link href="/bdm/appointments">Back to appointments</Link>
            </p>
          </div>
        )}
      </div>
    </PortalShell>
  );
}

import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmAppointmentsPanel from "@/components/BdmAppointmentsPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { appointmentTypes } from "@/lib/bdmAppointments";
import { BDM_NAV, BDM_SIGN_IN } from "@/lib/navigation";

// bdm-006: the BDM's own appointments (A3). The API is the gate.
export default async function BdmAppointmentsPage() {
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  const type = me.bdm_profile.bdm_type;
  return (
    <PortalShell nav={BDM_NAV} roleLabel={`${BDM_TYPE_LABEL[type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Appointments</div>
            <h2>Your appointments</h2>
            <p className="muted">Times are India time (IST).</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading appointments…</p>}>
          <BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={appointmentTypes(type)} />
        </Suspense>
      </div>
    </PortalShell>
  );
}

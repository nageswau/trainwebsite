import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import TripDecision from "@/components/TripDecision";
import TripDetails from "@/components/TripDetails";
import TripExpenses from "@/components/TripExpenses";
import { serverApi } from "@/lib/api";
import { APPROVAL_LABEL, TRAVEL_LABEL, type Trip } from "@/lib/bdmTravel";
import { BDM_MANAGER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// bdm-010: a team trip, read-only, with Approve/Reject when the API says this caller decides it (the BDM's manager, or a
// super_admin while that manager is inactive). A super_admin keeps the admin navigation (bdm-001 QA-12).
export default async function ManagerTripPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User, trip: Trip;
  try {
    [user, trip] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Trip>(`/api/v1/bdm/manager/trips/${encodeURIComponent(id)}`)]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const superAdmin = user.role === "super_admin";
  const back = superAdmin ? "/admin/bdm-travel-approvals" : "/bdm/manager/approvals";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : BDM_MANAGER_NAV} roleLabel={superAdmin ? "Super Administrator" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Travel · {trip.code} · {trip.bdm.full_name}</div>
            <h2>{trip.from_place} → {trip.to_place}</h2>
            <p>
              <span className="badge state-badge">Approval: {APPROVAL_LABEL[trip.approval_status]}</span>{" "}
              <span className="badge state-badge">Travel: {TRAVEL_LABEL[trip.travel_status]}</span>
            </p>
          </div>
          <Link className="btn secondary" href={back}>Back to approvals</Link>
        </div>
        <TripDecision trip={trip} />
        {trip.rejection_reason && (
          <div className="form-warning" role="note" style={{ marginTop: 16 }}>
            <strong>Reason given:</strong> <span style={{ whiteSpace: "pre-wrap" }}>{trip.rejection_reason}</span>
          </div>
        )}
        <section className="card" aria-labelledby="trip-details-heading" style={{ marginTop: 20 }}>
          <h3 id="trip-details-heading">Trip details</h3>
          <TripDetails trip={trip} />
        </section>
        <section className="card" aria-labelledby="trip-costs-heading" style={{ marginTop: 20 }}>
          <h3 id="trip-costs-heading">Costs and expenses</h3>
          <TripExpenses trip={trip} />
        </section>
        {trip.remarks && (
          <section className="card" aria-labelledby="trip-remarks-heading" style={{ marginTop: 20 }}>
            <h3 id="trip-remarks-heading">Remarks</h3>
            <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{trip.remarks}</p>
          </section>
        )}
      </div>
    </PortalShell>
  );
}

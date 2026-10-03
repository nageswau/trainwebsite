import Link from "next/link";

import { travelUnavailable } from "@/components/TravelUnavailable";
import PortalShell from "@/components/PortalShell";
import TripActions from "@/components/TripActions";
import TripDetails from "@/components/TripDetails";
import TripExpenses from "@/components/TripExpenses";
import TripForm from "@/components/TripForm";
import TripRemarks from "@/components/TripRemarks";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { APPROVAL_LABEL, TRAVEL_LABEL, indiaToday, type Trip } from "@/lib/bdmTravel";
import { BDM_NAV, BDM_SIGN_IN } from "@/lib/navigation";

// bdm-010 (§12.2 F2): one trip -- the next action first, then details, costs and expenses, and remarks. The editor appears only
// while the API says the trip is editable (draft or rejected); a trip that is not yours is the API's 404 on the access card.
export default async function TripPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let me: BdmMe, trip: Trip;
  try {
    [me, trip] = await Promise.all([serverApi<BdmMe>("/api/v1/bdm/me"), serverApi<Trip>(`/api/v1/bdm/trips/${encodeURIComponent(id)}`)]);
  } catch (e) {
    return travelUnavailable(e, BDM_SIGN_IN, `/bdm/travel/${encodeURIComponent(id)}`);
  }
  return (
    <PortalShell nav={BDM_NAV} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Travel · {trip.code}</div>
            <h2 style={{ overflowWrap: "anywhere" }}>{trip.from_place} → {trip.to_place}</h2>
            <p>
              <span className="badge state-badge">Approval: {APPROVAL_LABEL[trip.approval_status]}</span>{" "}
              <span className="badge state-badge">Travel: {TRAVEL_LABEL[trip.travel_status]}</span>
            </p>
          </div>
          <Link className="btn secondary" href="/bdm/travel">Back to my trips</Link>
        </div>
        {trip.rejection_reason && (
          <div className="form-warning" role="note" style={{ marginBottom: 16 }}>
            <strong>Not approved.</strong> <span style={{ whiteSpace: "pre-wrap" }}>{trip.rejection_reason}</span> Edit the trip and submit it again.
          </div>
        )}
        <TripActions trip={trip} />
        <section className="card" aria-labelledby="trip-details-heading" style={{ marginTop: 20 }}>
          <h3 id="trip-details-heading">Trip details</h3>
          <TripDetails trip={trip} />
        </section>
        {trip.can_edit && (
          <section className="card" aria-labelledby="trip-edit-heading" style={{ marginTop: 20 }}>
            <h3 id="trip-edit-heading">Edit trip</h3>
            <TripForm trip={trip} today={indiaToday()} />
          </section>
        )}
        <section className="card" aria-labelledby="trip-costs-heading" style={{ marginTop: 20 }}>
          <h3 id="trip-costs-heading">Costs and expenses</h3>
          <TripExpenses trip={trip} />
        </section>
        <section className="card" aria-labelledby="trip-remarks-heading" style={{ marginTop: 20 }}>
          <h3 id="trip-remarks-heading">Remarks</h3>
          <TripRemarks trip={trip} />
        </section>
      </div>
    </PortalShell>
  );
}

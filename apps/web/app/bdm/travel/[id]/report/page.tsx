import PortalShell from "@/components/PortalShell";
import TripReport, { ReportTitle } from "@/components/TripReport";
import { tripNotFound, travelUnavailable } from "@/components/TravelUnavailable";
import { ApiError, serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { isUuid, type Trip } from "@/lib/bdmTravel";
import { bdmNav } from "@/lib/bdmNav";
import { BDM_SIGN_IN } from "@/lib/navigation";

// bdm-011 (AC3): the travel report of one of the BDM's own trips, available once it is completed. Before that the API answers 409
// with the reason, shown here with the way back to the trip.
export default async function TripReportPage({ params }: { params: Promise<{ id: string }> }) {
  const nav = bdmNav(); // the unread badge, read alongside the page's own data (never rejects)
  const { id } = await params;
  if (!isUuid(id)) return tripNotFound(BDM_SIGN_IN);
  const tripHref = `/bdm/travel/${id}`;
  let me: BdmMe;
  let trip: Trip | null = null;
  let notYet: string | null = null;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return travelUnavailable(e, BDM_SIGN_IN, `${tripHref}/report`);
  }
  try {
    trip = await serverApi<Trip>(`/api/v1/bdm/trips/${id}/report`);
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 409)) return travelUnavailable(e, BDM_SIGN_IN, `${tripHref}/report`);
    notYet = e.message;
  }
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <ReportTitle trip={trip} tripHref={tripHref} />
        {trip ? <TripReport trip={trip} view="owner" /> : <p className="card" role="status">{notYet}</p>}
      </div>
    </PortalShell>
  );
}

import { tripNotFound, travelUnavailable } from "@/components/TravelUnavailable";
import PortalShell from "@/components/PortalShell";
import TripWorkspace from "@/components/TripWorkspace";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { indiaToday, isUuid, type Trip } from "@/lib/bdmTravel";
import { bdmNav } from "@/lib/bdmNav";
import { BDM_SIGN_IN } from "@/lib/navigation";

// bdm-010: one of the BDM's own trips. The server reads it once; TripWorkspace owns it from there (QA10-16) -- actions, details,
// the editor while draft/rejected, costs and expenses, remarks. A trip that is not yours is the API's 404 on the access card; a
// malformed link is the same card without asking the API (QA10-04).
export default async function TripPage({ params }: { params: Promise<{ id: string }> }) {
  const nav = bdmNav(); // the unread badge, read alongside the page's own data (never rejects)
  const { id } = await params;
  if (!isUuid(id)) return tripNotFound(BDM_SIGN_IN);
  let me: BdmMe, trip: Trip;
  try {
    [me, trip] = await Promise.all([serverApi<BdmMe>("/api/v1/bdm/me"), serverApi<Trip>(`/api/v1/bdm/trips/${id}`)]);
  } catch (e) {
    return travelUnavailable(e, BDM_SIGN_IN, `/bdm/travel/${id}`);
  }
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <TripWorkspace initialTrip={trip} view="owner" today={indiaToday()} backHref="/bdm/travel" backLabel="Back to my trips" />
      </div>
    </PortalShell>
  );
}

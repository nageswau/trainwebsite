import Link from "next/link";

import { travelUnavailable } from "@/components/TravelUnavailable";
import PortalShell from "@/components/PortalShell";
import TripForm from "@/components/TripForm";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { indiaToday } from "@/lib/bdmTravel";
import { bdmNav } from "@/lib/bdmNav";
import { BDM_SIGN_IN } from "@/lib/navigation";

// bdm-010: a new trip starts as a draft; the BDM submits it for approval from its page.
export default async function NewTripPage() {
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return travelUnavailable(e, BDM_SIGN_IN, "/bdm/travel/new");
  }
  return (
    <PortalShell nav={await bdmNav()} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Travel</div>
            <h2>New trip</h2>
            <p className="muted">Saved as a draft. You can edit it until you submit it for approval.</p>
          </div>
          <Link className="btn secondary" href="/bdm/travel">Back to my trips</Link>
        </div>
        <div className="card">
          <TripForm today={indiaToday()} />
        </div>
      </div>
    </PortalShell>
  );
}

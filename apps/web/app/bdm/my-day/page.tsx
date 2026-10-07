import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmProfileCard from "@/components/BdmProfileCard";
import MeetingRequestsCard from "@/components/MeetingRequestsCard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { bdmNav } from "@/lib/bdmNav";
import { BDM_REQUESTS_URL, type RequestPage } from "@/lib/meetingRequests";
import { BDM_SIGN_IN } from "@/lib/navigation";

async function pendingRequests(): Promise<RequestPage | null> {
  try {
    return await serverApi<RequestPage>(`${BDM_REQUESTS_URL}?status=pending&limit=5`);
  } catch {
    return null;
  }
}

// bdm-001 (AC05, B2): the BDM landing page -- a minimal shell; bdm-014 fills My Day. The API is the gate: any other role, or a BDM
// without a profile, gets its 403 message here with a link home.
export default async function BdmMyDayPage() {
  const nav = bdmNav(); // the unread badge, read alongside the page's own data (never rejects)
  const requests = pendingRequests(); // tel-019: the Requests inbox card, likewise (never rejects)
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">My Day</div>
            <h2>Welcome, {me.full_name}</h2>
            <p className="muted">Your appointments, travel and follow-ups will appear here.</p>
          </div>
        </div>
        <MeetingRequestsCard page={await requests} />
        <BdmProfileCard me={me} />
      </div>
    </PortalShell>
  );
}

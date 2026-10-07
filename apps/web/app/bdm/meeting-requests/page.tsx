import { accessUnavailable } from "@/components/AccessUnavailable";
import MeetingRequestList from "@/components/MeetingRequestList";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { bdmNav } from "@/lib/bdmNav";
import { BDM_REQUESTS_URL, listParams, type RequestPage } from "@/lib/meetingRequests";
import { BDM_SIGN_IN } from "@/lib/navigation";

// tel-019 (MR11): the BDM's meeting-request inbox -- their module's open pool plus the requests that are theirs. Pending is the default.
export default async function BdmMeetingRequestsPage({ searchParams }: { searchParams: Promise<{ status?: string; offset?: string }> }) {
  const nav = bdmNav(); // the unread badge, read alongside the page's own data (never rejects)
  const params = await searchParams;
  const { status, query } = listParams({ ...params, status: params.status ?? "pending" }); // ?status=all -> no filter
  let me: BdmMe;
  let page: RequestPage;
  try {
    [me, page] = await Promise.all([serverApi<BdmMe>("/api/v1/bdm/me"), serverApi<RequestPage>(`${BDM_REQUESTS_URL}?${query}`)]);
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  const type = me.bdm_profile.bdm_type;
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Requests</div>
            <h2>Meeting requests</h2>
            <p className="muted">Telecallers ask for {BDM_TYPE_LABEL[type].toLowerCase()} meetings here. Open a request to accept it into an appointment or decline it.</p>
          </div>
        </div>
        <MeetingRequestList page={page} basePath="/bdm/meeting-requests" status={status} viewer="bdm" defaultStatus="pending" />
      </div>
    </PortalShell>
  );
}

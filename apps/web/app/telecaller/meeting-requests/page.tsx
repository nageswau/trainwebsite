import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import MeetingRequestList from "@/components/MeetingRequestList";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { listParams, type RequestPage, TEL_REQUESTS_URL } from "@/lib/meetingRequests";
import { TELECALLER_SIGN_IN } from "@/lib/navigation";
import { telecallerNav } from "@/lib/telecallerNav";
import { teamRoleLabel, type TelecallerMe } from "@/lib/telecaller";

// tel-019 (MR12): the telecaller's own BDM meeting requests and what became of them. The API is the gate.
export default async function TelecallerMeetingRequestsPage({ searchParams }: { searchParams: Promise<{ status?: string; offset?: string; filed?: string }> }) {
  const params = await searchParams;
  const { status, query } = listParams(params);
  let me: TelecallerMe;
  let page: RequestPage;
  try {
    [me, page] = await Promise.all([serverApi<TelecallerMe>("/api/v1/telecaller/me"), serverApi<RequestPage>(`${TEL_REQUESTS_URL}?${query}`)]);
  } catch (e) {
    return accessUnavailable(e, TELECALLER_SIGN_IN);
  }
  return (
    <PortalShell nav={await telecallerNav()} roleLabel={teamRoleLabel(me.telecaller_profile.team)} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">BDM requests</div>
            <h2>BDM meeting requests</h2>
            <p className="muted">Ask a BDM to meet a college, agent, school or company. You&apos;ll see here when it is accepted or declined.</p>
          </div>
          <Link className="btn" href="/telecaller/meeting-requests/new">New request</Link>
        </div>
        {params.filed !== undefined && (
          <p className="form-success" role="status">Request {params.filed} sent. It stays Pending until a BDM accepts or declines it.</p>
        )}
        <MeetingRequestList page={page} basePath="/telecaller/meeting-requests" status={status} viewer="telecaller" />
      </div>
    </PortalShell>
  );
}

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import MeetingRequestList from "@/components/MeetingRequestList";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { bdmManagerNav } from "@/lib/bdmNav";
import { BDM_REQUESTS_URL, listParams, type RequestPage } from "@/lib/meetingRequests";
import type { User } from "@/lib/types";

// tel-019 (MR3): the meeting requests for this manager's team plus the open pool (super_admin: all), read-only.
export default async function BdmManagerMeetingRequestsPage({ searchParams }: { searchParams: Promise<{ status?: string; offset?: string }> }) {
  const nav = bdmManagerNav();
  const { status, query } = listParams(await searchParams);
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
  let page: RequestPage;
  try {
    page = await serverApi<RequestPage>(`${BDM_REQUESTS_URL}?${query}`);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={await nav} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Requests</div>
            <h2>Meeting requests</h2>
            <p className="muted">Read-only: requests for your team&apos;s BDMs and the open requests any BDM of the module can take. Times are India time (IST).</p>
          </div>
        </div>
        <MeetingRequestList page={page} basePath="/bdm/manager/meeting-requests" status={status} viewer="manager" />
      </div>
    </PortalShell>
  );
}

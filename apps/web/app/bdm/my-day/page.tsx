import Link from "next/link";
import { redirect } from "next/navigation";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmMyDay from "@/components/BdmMyDay";
import MeetingRequestsCard from "@/components/MeetingRequestsCard";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { isMyDay, MY_DAY_URL, type MyDay } from "@/lib/bdmMyDay";
import { bdmNav } from "@/lib/bdmNav";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { BDM_REQUESTS_URL, type RequestPage } from "@/lib/meetingRequests";
import { BDM_SIGN_IN, dashboardPathFor } from "@/lib/navigation";
import type { User } from "@/lib/types";

/** K10: a BDM manager who lands here (the API refuses them) belongs on the manager dashboard. */
async function managerHome(error: unknown): Promise<string | null> {
  if (!(error instanceof ApiError && error.status === 403)) return null;
  const user = await serverApi<User>("/api/v1/auth/me").catch(() => null);
  return user?.role === "bdm_manager" ? dashboardPathFor(user) : null;
}

// bdm-014 (DEC-SCOPE-097): the BDM landing page -- today's appointments, upcoming travel, follow-ups and the type's overview tiles.
// `/bdm/me` is the gate (bdm-001); a day that can't be read after it loaded is shown inline with "Try again".
export default async function BdmMyDayPage() {
  const nav = bdmNav(); // the unread badge, read alongside the page's own data (never rejects)
  // tel-019: the meeting-request inbox card, likewise read alongside (never rejects; null = couldn't read)
  const requests = serverApi<RequestPage>(`${BDM_REQUESTS_URL}?status=pending&limit=5`).catch(() => null);
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    const home = await managerHome(e);
    if (home) redirect(home);
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  const data = await serverApi<MyDay>(MY_DAY_URL).then((d) => (isMyDay(d) ? d : null), () => null);
  const profile = me.bdm_profile;
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">My Day</div>
            <h2>Welcome, {me.full_name}</h2>
            <p className="muted">
              Employee ID {profile.employee_id}{profile.territory ? ` · ${profile.territory}` : ""} ·{" "}
              <Link href="/bdm/profile" style={LINK_STYLE}>View profile</Link>
            </p>
            <p className="muted">Times are India time (IST).</p>
          </div>
        </div>
        {data ? (
          <BdmMyDay data={data} />
        ) : (
          <div className="card" role="alert">
            <p className="form-error">Unable to load your day.</p>
            <Link href="/bdm/my-day" className="btn secondary small">Try again</Link>
          </div>
        )}
        <MeetingRequestsCard page={await requests} />
      </div>
    </PortalShell>
  );
}

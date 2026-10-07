import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import TelecallerActivityPanel from "@/components/TelecallerActivityPanel";
import { ApiError, serverApi } from "@/lib/api";
import { TELECALLER_MANAGER_NAV } from "@/lib/navigation";
import { activityError, activityUrl, dayParam, type TelecallerActivity } from "@/lib/telecallerMetrics";
import { istToday } from "@/lib/telecallerTargets";
import type { User } from "@/lib/types";

// tel-021 (DB6, T23): a manager's view of one direct report's daily activity (super_admin: any telecaller). The API decides the scope:
// someone else's telecaller is a 404, shown here as "not one of your reports"; a refused day (future) is a note in the panel.
export default async function TelecallerReportActivityPage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ date?: string }>;
}) {
  const [{ id }, { date }] = await Promise.all([params, searchParams]);
  const day = dayParam(date);
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  let activity: TelecallerActivity | null = null;
  let failure = "";
  let missing = false;
  try {
    activity = await serverApi<TelecallerActivity>(activityUrl(day, id));
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) return accessUnavailable(e, "/admin/login");
    missing = e instanceof ApiError && e.status === 404;
    failure = activityError(e);
  }
  const today = istToday();
  return (
    <PortalShell nav={TELECALLER_MANAGER_NAV} roleLabel="Telecaller Manager" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Team · Daily activity</div>
            <h2>{activity ? activity.user.full_name : "Daily activity"}</h2>
          </div>
          <Link className="btn secondary small" href="/telecaller/manager/team">Back to team</Link>
        </div>
        {missing ? (
          <p className="empty" role="status">This telecaller is not one of your reports.</p>
        ) : (
          <TelecallerActivityPanel activity={activity} error={failure} day={day ?? today} today={today} />
        )}
      </div>
    </PortalShell>
  );
}

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmCalendar from "@/components/BdmCalendar";
import BdmCalendarPicker from "@/components/BdmCalendarPicker";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { todayIst } from "@/lib/bdmAppointments";
import { apiPath, type CalendarData, isCalendarData, parseDate, parseView, rangeOf } from "@/lib/bdmCalendar";
import { bdmManagerNav } from "@/lib/bdmNav";
import type { User } from "@/lib/types";

type Search = Promise<{ view?: string | string[]; date?: string | string[]; bdm?: string | string[] }>;
type Read = { data: CalendarData | null; notOnTeam: boolean };

// bdm-013 (K3): a team BDM's calendar, read-only (super_admin: any BDM). The API decides the team: 404 (or 422 for a malformed id)
// reads "not on your team"; any other failure is the calendar's inline error.
async function read(path: string): Promise<Read> {
  try {
    const d = await serverApi<CalendarData>(path);
    return { data: isCalendarData(d) ? d : null, notOnTeam: false };
  } catch (e) {
    return { data: null, notOnTeam: e instanceof ApiError && (e.status === 404 || e.status === 422) };
  }
}

export default async function BdmManagerCalendarPage({ searchParams }: { searchParams: Search }) {
  const nav = bdmManagerNav(); // the unread badge, read alongside the page's own data (never rejects)
  const params = await searchParams;
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
  const view = parseView(params.view);
  const date = parseDate(params.date, todayIst());
  const bdm = typeof params.bdm === "string" && params.bdm ? params.bdm : null;
  const { from, to } = rangeOf(view, date);
  const result = bdm ? await read(apiPath(from, to, bdm)) : null;
  const current = result?.data ? { id: result.data.bdm.id, label: result.data.bdm.full_name } : null;
  return (
    <PortalShell nav={await nav} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Calendar</div>
            <h2>{current ? `${current.label}'s calendar` : "Team calendar"}</h2>
            <p className="muted">Read-only. Times are India time (IST).</p>
          </div>
        </div>
        <BdmCalendarPicker view={view} date={date} current={current} />
        {!bdm ? (
          <p className="empty" role="status">Choose a BDM to see their calendar.</p>
        ) : result?.notOnTeam ? (
          <p className="form-error" role="alert">This BDM is not on your team.</p>
        ) : (
          <BdmCalendar data={result?.data ?? null} view={view} date={date} basePath="/bdm/manager/calendar" managerOf={bdm} />
        )}
      </div>
    </PortalShell>
  );
}

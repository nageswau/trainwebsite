import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PartnershipCalendar from "@/components/PartnershipCalendar";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { todayIst } from "@/lib/bdmAppointments";
import {
  apiPath, CALENDAR_PATH, CALENDAR_URL, EVENT_CREATORS, isCalendarData, NEW_EVENT_PATH, parseDate, parseView, type PartnershipCalendarData, rangeOf,
} from "@/lib/partnershipCalendar";
import type { ManagerRef } from "@/lib/telecaller";
import type { User } from "@/lib/types";
import { shellFor } from "@/lib/universities";

type Search = Promise<{ view?: string | string[]; date?: string | string[]; employee?: string | string[] }>;
type Read = { data: PartnershipCalendarData | null; notFound: boolean };

// upc-011 (§9, CL9/CL13): meetings, visits and partnership events on one calendar (?view=week|month&date=YYYY-MM-DD&employee=<id>). A
// manager sees their own; a head their team, or one person from it; super_admin everyone. The employee choice is a plain GET form, so it
// works without JavaScript. The API is the gate: a 403 is the shell's access page, a 404 for the chosen person reads "not in your team".
async function read(path: string): Promise<Read> {
  try {
    const d = await serverApi<PartnershipCalendarData>(path);
    return { data: isCalendarData(d) ? d : null, notFound: false };
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) throw e;
    return { data: null, notFound: e instanceof ApiError && (e.status === 404 || e.status === 422) };
  }
}

export default async function PartnershipCalendarPage({ searchParams }: { searchParams: Search }) {
  const params = await searchParams;
  const view = parseView(params.view);
  const date = parseDate(params.date, todayIst());
  const employee = typeof params.employee === "string" && params.employee ? params.employee : undefined;
  const { from, to } = rangeOf(view, date);
  let user: User, result: Read, people: ManagerRef[];
  try {
    [user, result, people] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      read(apiPath(from, to, employee)),
      serverApi<{ items: ManagerRef[] }>(`${CALENDAR_URL}/employees`).then((r) => r.items, () => []),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const chooses = user.role !== "partnership_manager";
  const chosen = result.data?.employee;
  const heading = chosen && chosen.id !== user.id ? `${chosen.full_name}'s calendar` : chooses && !chosen ? (user.role === "super_admin" ? "Everyone's calendar" : "Team calendar") : "Your calendar";
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Calendar</div>
            <h2>{heading}</h2>
            <p className="muted">University meetings, university visits, conferences, education fairs, partner meetings, MoU signings, webinars and university presentations. Read-only; open an item to change it. Times are India time (IST).</p>
          </div>
          {EVENT_CREATORS.has(user.role) && <div className="actions"><Link className="btn" href={NEW_EVENT_PATH} style={{ whiteSpace: "nowrap" }}>Add an event</Link></div>}
        </div>
        {chooses && people.length > 0 && (
          <form method="get" action={CALENDAR_PATH} className="card" aria-label="Choose whose calendar" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end", padding: 14, marginBottom: 16 }}>
            <input type="hidden" name="view" value={view} />
            <input type="hidden" name="date" value={date} />
            <div className="field" style={{ margin: 0, minWidth: 220 }}>
              <label htmlFor="calendar-employee">Employee</label>
              <select id="calendar-employee" name="employee" defaultValue={employee ?? ""}>
                <option value="">{user.role === "super_admin" ? "Everyone" : "My whole team"}</option>
                {people.map((p) => <option key={p.id} value={p.id}>{p.full_name}{p.active ? "" : " (inactive)"}</option>)}
              </select>
            </div>
            <button type="submit" className="btn secondary small">Show</button>
          </form>
        )}
        {result.notFound ? (
          <p className="form-error" role="alert">This person is not in your team. <Link href={CALENDAR_PATH}>Show the whole calendar</Link></p>
        ) : (
          <PartnershipCalendar data={result.data} view={view} date={date} employee={employee} />
        )}
      </div>
    </PortalShell>
  );
}

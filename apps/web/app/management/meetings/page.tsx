import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import DiscussionsShell from "@/components/DiscussionsShell";
import ManagementMeetingCalendar, { MeetingRow } from "@/components/ManagementMeetingCalendar";
import { ApiError, serverApi } from "@/lib/api";
import { indiaToday } from "@/lib/bdmTravel";
import type { ManagementMe } from "@/lib/management";
import { calendarUrl, MEETINGS_API, MEETINGS_HOME, type MeetingPage } from "@/lib/managementMeetings";
import { parseDate, parseView, rangeOf } from "@/lib/partnershipCalendar";

// mgmt-029 (EVID-017 §29, MM11/MM12): Today's meetings, then the meeting calendar (week or month). The API refuses everyone outside the
// operational tier (the accountant included, M13), and the page then shows the access card. Either read failing leaves the other usable.
export default async function ManagementMeetingsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const search = await searchParams;
  const today = indiaToday();
  const view = parseView(search.view);
  const date = parseDate(search.date, today);
  const { from, to } = rangeOf(view, date);
  let me: ManagementMe;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const read = async (url: string): Promise<MeetingPage | null> => {
    try {
      return await serverApi<MeetingPage>(url);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) throw e;
      return null;
    }
  };
  let todays: MeetingPage | null;
  let calendar: MeetingPage | null;
  try {
    [todays, calendar] = await Promise.all([read(MEETINGS_API), read(calendarUrl(from, to))]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <DiscussionsShell me={me} section="Meetings" title="Management meetings" actions={<Link className="btn" href={`${MEETINGS_HOME}/new`}>New meeting</Link>}
      intro="Partner, department, school, university, agent and recruiter meetings and marketing reviews. Each meeting's minutes lead to its decisions and tasks.">
      <section aria-labelledby="todays-meetings" className="action-card">
        <h3 id="todays-meetings" style={{ marginTop: 0 }}>Today&apos;s meetings</h3>
        {todays === null ? (
          <p className="form-error" role="alert">Meetings are unavailable right now. Please try again.</p>
        ) : todays.items.length === 0 ? (
          <p className="empty" role="status">No meetings today.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>{todays.items.map((m) => <MeetingRow key={m.id} meeting={m} />)}</ul>
        )}
      </section>
      <ManagementMeetingCalendar data={calendar} view={view} date={date} />
    </DiscussionsShell>
  );
}

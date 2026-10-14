import Link from "next/link";

import { dayTitle, rangeTitle } from "@/lib/bdmCalendar";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { calendarHref, istTime, KIND_LABEL, MEETINGS_HOME, meetingsOn, STATUS_LABEL, statusClass, type Meeting, type MeetingPage } from "@/lib/managementMeetings";
import { type CalendarView, rangeDays, rangeOf, stepDate } from "@/lib/partnershipCalendar";

// mgmt-029 (MM11): the meeting calendar. A list of days -- never a canvas or a fixed-width grid -- so it reflows to one column on a
// phone; every control is a plain link, so it works with the keyboard and the browser history (bdm-013 / upc-011's layout). The week
// lists every day; the month lists only days with a meeting.
const ROW = { display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", padding: "8px 0", borderTop: "1px solid var(--line, #e5e7eb)" } as const;
const LINK = { ...LINK_STYLE, overflowWrap: "anywhere" } as const;

/** One meeting as a row: kind, IST time, the title as a link to the meeting, and its status unless scheduled. Shared with Today's meetings. */
export function MeetingRow({ meeting }: { meeting: Meeting }) {
  return (
    <li style={ROW}>
      <span className="badge">{KIND_LABEL[meeting.kind]}</span>
      <span>{istTime(meeting.starts_at)} IST</span>
      <Link href={`${MEETINGS_HOME}/${meeting.id}`} style={LINK}>{meeting.title}</Link>
      <span className="muted" style={{ fontSize: 14 }}>{meeting.mode}{meeting.location ? ` · ${meeting.location}` : ""}</span>
      {meeting.status !== "scheduled" && <span className={statusClass(meeting.status)}>{STATUS_LABEL[meeting.status]}</span>}
    </li>
  );
}

export default function ManagementMeetingCalendar({ data, view, date }: { data: MeetingPage | null; view: CalendarView; date: string }) {
  const { from, to } = rangeOf(view, date);
  const days = rangeDays(view, date).filter((day) => view === "week" || (data !== null && meetingsOn(data.items, day).length > 0));
  return (
    <div className="action-card wide">
      <nav aria-label="Calendar" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>{rangeTitle(from, to)}</h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {(["week", "month"] as const).map((v) => (
            <Link key={v} href={calendarHref(v, date)} aria-current={view === v ? "page" : undefined} className={`btn small${view === v ? "" : " secondary"}`}>
              {v === "week" ? "Week" : "Month"}
            </Link>
          ))}
          <Link href={calendarHref(view, stepDate(view, date, -1))} className="btn small secondary">Previous {view}</Link>
          {data && <Link href={calendarHref(view, data.today)} className="btn small secondary">Today</Link>}
          <Link href={calendarHref(view, stepDate(view, date, 1))} className="btn small secondary">Next {view}</Link>
        </div>
      </nav>
      {data === null ? (
        <div role="alert" style={{ marginTop: 12 }}>
          <p className="form-error">Unable to load the calendar.</p>
          <Link href={calendarHref(view, date)} className="btn secondary small">Try again</Link>
        </div>
      ) : (
        <>
          {data.items.length === 0 && <p className="empty" role="status">No meetings this {view}.</p>}
          {days.map((day) => {
            const items = meetingsOn(data.items, day);
            return (
              <section key={day} aria-labelledby={`meetings-${day}`} style={{ padding: "12px 0", borderTop: "2px solid var(--line, #e5e7eb)" }}>
                <h4 id={`meetings-${day}`} style={{ margin: 0, fontSize: 16 }}>
                  {dayTitle(day)}
                  {day === data.today ? <> <span className="badge">Today</span></> : null}
                  {items.length === 0 && <span className="muted" style={{ fontWeight: 400 }}> — No meetings</span>}
                </h4>
                {items.length > 0 && <ul style={{ listStyle: "none", padding: 0, margin: "4px 0 0" }}>{items.map((m) => <MeetingRow key={m.id} meeting={m} />)}</ul>}
              </section>
            );
          })}
        </>
      )}
    </div>
  );
}

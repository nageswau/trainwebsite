import Link from "next/link";

import { STATUS_CLASS, STATUS_LABEL, TYPE_LABEL, type AppointmentStatus, formatMinutes } from "@/lib/bdmAppointments";
import {
  addDays, type CalendarData, type CalendarView, dayItems, daysOf, dayTitle, headline, itemHref, pageHref, rangeOf, rangeTitle, type TripRole,
} from "@/lib/bdmCalendar";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { SCHOOL_TIME_ZONE } from "@/lib/formatDate";

// bdm-013 (DEC-SCOPE-078 §7): the read-only calendar. A list of days -- never a canvas or a fixed-width grid -- so it reflows to one
// column on a phone (AC4); every control is a plain link, so it works with the keyboard and the browser history (AC5).
type Props = { data: CalendarData | null; view: CalendarView; date: string; basePath: string; managerOf: string | null };

const ROW = { display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", padding: "8px 0", borderTop: "1px solid var(--line, #e5e7eb)" } as const;
const LINK = { ...LINK_STYLE, overflowWrap: "anywhere" } as const; // QA13-01: item links must read as links
const ROLE_TEXT: Record<TripRole, string> = { departs: "Departs", away: "Away", returns: "Return travel", "day trip": "Day trip" };
const TRIP_STATUS: Record<string, string> = { draft: "Draft", submitted: "Submitted", in_progress: "In progress", completed: "Completed" };

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: SCHOOL_TIME_ZONE });
const tripStatus = (approval: string, travel: string) => (approval === "approved" ? TRIP_STATUS[travel] : TRIP_STATUS[approval]);

function renderDay(data: CalendarData, day: string, managerOf: string | null) {
  const items = dayItems(data, day);
  const empty = !items.trips.length && !items.appointments.length && !items.tasks.length;
  return (
    <section key={day} aria-labelledby={`cal-${day}`} style={{ padding: "12px 0", borderTop: "2px solid var(--line, #e5e7eb)" }}>
      <h4 id={`cal-${day}`} style={{ margin: 0, fontSize: 16, overflowWrap: "anywhere" }}>
        {dayTitle(day)}
        {day === data.today ? <> <span className="badge">Today</span></> : null}
        {" — "}
        {headline(data, day)}
      </h4>
      {!empty && (
        <ul style={{ listStyle: "none", padding: 0, margin: "4px 0 0" }}>
          {items.trips.map(({ trip, role }) => {
            const status = tripStatus(trip.approval_status, trip.travel_status);
            return (
              <li key={trip.id} style={ROW}>
                <span className="badge">Trip</span>
                <Link href={itemHref("trip", trip, managerOf)} style={LINK}>Trip {trip.code}</Link>
                <span style={{ overflowWrap: "anywhere" }}>{trip.from_place} → {trip.to_place} · {ROLE_TEXT[role]}</span>
                {status && <span className="status pending">{status}</span>}
              </li>
            );
          })}
          {items.appointments.map((a) => (
            <li key={a.id} style={ROW}>
              <span className="badge">{a.seminar ? "Seminar" : "Appointment"}</span>
              <span>{time(a.starts_at)} · {formatMinutes(a.duration_minutes)}</span>
              <Link href={itemHref("appointment", a, managerOf)} style={LINK}>
                {TYPE_LABEL[a.appointment_type] ?? a.appointment_type} — {a.organization.name}
              </Link>
              {a.status !== "scheduled" && (
                <span className={STATUS_CLASS[a.status as AppointmentStatus] ?? "status"}>{STATUS_LABEL[a.status as AppointmentStatus] ?? a.status}</span>
              )}
            </li>
          ))}
          {items.tasks.map((t) => (
            <li key={t.id} style={ROW}>
              <span className="badge">{t.kind === "task" ? "Task" : "Follow-up"}</span>
              <Link href={itemHref("task", t, managerOf)} style={LINK}>
                {t.title}{t.organization ? ` — ${t.organization.name}` : ""}
              </Link>
              {t.status === "done" && <span className="status">Done</span>}
              {t.overdue && <span className="status error">Overdue</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function BdmCalendar({ data, view, date, basePath, managerOf }: Props) {
  const bdm = managerOf ?? undefined;
  const step = view === "week" ? 7 : 1;
  const { from, to } = rangeOf(view, date);
  const href = (next: { view?: CalendarView; date?: string }) => pageHref(basePath, { view: next.view ?? view, date: next.date ?? date, bdm });
  const days = daysOf(from, to);
  const nothing = data !== null && !data.appointments.length && !data.trips.length && !data.tasks.length;
  return (
    <div className="action-card wide">
      <nav aria-label="Calendar" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>{rangeTitle(from, to)}</h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {(["day", "week"] as const).map((v) => (
            <Link key={v} href={href({ view: v })} aria-current={view === v ? "page" : undefined} className={`btn small${view === v ? "" : " secondary"}`}>
              {v === "day" ? "Day" : "Week"}
            </Link>
          ))}
          <Link href={href({ date: addDays(date, -step) })} className="btn small secondary">Previous {view}</Link>
          {data && <Link href={href({ date: data.today })} className="btn small secondary">Today</Link>}
          <Link href={href({ date: addDays(date, step) })} className="btn small secondary">Next {view}</Link>
        </div>
      </nav>
      {data === null ? (
        <div role="alert" style={{ marginTop: 12 }}>
          <p className="form-error">Unable to load the calendar.</p>
          <Link href={href({})} className="btn secondary small">Try again</Link>
        </div>
      ) : (
        <>
          {data.truncated && <p className="muted" role="status">Some items are not shown. Choose a shorter range.</p>}
          {nothing && <p className="empty" role="status">Nothing planned this {view}.</p>}
          {days.map((day) => renderDay(data, day, managerOf))}
        </>
      )}
    </div>
  );
}

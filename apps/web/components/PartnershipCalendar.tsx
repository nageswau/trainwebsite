import Link from "next/link";

import { dayTitle, rangeTitle } from "@/lib/bdmCalendar";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import { MEETING_STATUSES } from "@/lib/meetings";
import {
  type CalendarItem, type CalendarView, datesText, itemHref, itemsOn, KIND_LABELS, overlapText, pageHref, type PartnershipCalendarData,
  rangeDays, rangeOf, stepDate,
} from "@/lib/partnershipCalendar";
import { statusText } from "@/lib/visits";

// upc-011 (§9, CL13): the read-only partnership calendar. A list of days -- never a canvas or a fixed-width grid -- so it reflows to one
// column on a phone; every control is a plain link, so it works with the keyboard and the browser history (bdm-013's layout). The week
// lists every day; the month lists only days with something on them. Overlaps are flagged on the item (AC2).
type Props = { data: PartnershipCalendarData | null; view: CalendarView; date: string; employee?: string };

const ROW = { display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", padding: "8px 0", borderTop: "1px solid var(--line, #e5e7eb)" } as const;
const LINK = { ...LINK_STYLE, overflowWrap: "anywhere" } as const;

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: SCHOOL_TIME_ZONE });

function when(item: CalendarItem): string {
  if (item.starts_at) return `${time(item.starts_at)} IST`;
  return item.starts_on === item.ends_on ? "All day" : datesText(item.starts_on, item.ends_on);
}

function status(item: CalendarItem): string | null {
  if (item.source === "meeting") return item.status === "scheduled" ? null : MEETING_STATUSES[item.status] ?? item.status;
  if (item.source === "visit") return statusText({ status: item.status, approval_state: null });
  return null; // a cancelled event never reaches the calendar
}

function renderItem(item: CalendarItem) {
  const label = status(item);
  return (
    <li key={`${item.source}-${item.id}`} style={ROW}>
      <span className="badge">{KIND_LABELS[item.kind] ?? item.kind}</span>
      <span>{when(item)}</span>
      <Link href={itemHref(item)} style={LINK}>{item.code} — {item.title}</Link>
      {label && <span className="status pending">{label}</span>}
      {item.people.length > 0 && <span className="muted" style={{ overflowWrap: "anywhere" }}>{item.people.map((p) => p.full_name).join(", ")}</span>}
      {item.overlaps.length > 0 && (
        <span className="status error" style={{ flexBasis: "100%" }}>
          Overlap: {item.overlaps.map(overlapText).join("; ")}
        </span>
      )}
    </li>
  );
}

function renderDay(data: PartnershipCalendarData, day: string, items: CalendarItem[]) {
  return (
    <section key={day} aria-labelledby={`cal-${day}`} style={{ padding: "12px 0", borderTop: "2px solid var(--line, #e5e7eb)" }}>
      <h4 id={`cal-${day}`} style={{ margin: 0, fontSize: 16, overflowWrap: "anywhere" }}>
        {dayTitle(day)}
        {day === data.today ? <> <span className="badge">Today</span></> : null}
        {items.length === 0 && <span className="muted" style={{ fontWeight: 400 }}> — Nothing planned</span>}
      </h4>
      {items.length > 0 && <ul style={{ listStyle: "none", padding: 0, margin: "4px 0 0" }}>{items.map(renderItem)}</ul>}
    </section>
  );
}

export default function PartnershipCalendar({ data, view, date, employee }: Props) {
  const { from, to } = rangeOf(view, date);
  const href = (next: { view?: CalendarView; date?: string }) => pageHref({ view: next.view ?? view, date: next.date ?? date, employee });
  const days = rangeDays(view, date).map((day) => [day, data ? itemsOn(data.items, day) : []] as const);
  const shown = view === "week" ? days : days.filter(([, items]) => items.length > 0);
  const overlapping = data?.items.filter((i) => i.overlaps.length > 0).length ?? 0;
  return (
    <div className="action-card wide">
      <nav aria-label="Calendar" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>{rangeTitle(from, to)}</h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {(["week", "month"] as const).map((v) => (
            <Link key={v} href={href({ view: v })} aria-current={view === v ? "page" : undefined} className={`btn small${view === v ? "" : " secondary"}`}>
              {v === "week" ? "Week" : "Month"}
            </Link>
          ))}
          <Link href={href({ date: stepDate(view, date, -1) })} className="btn small secondary">Previous {view}</Link>
          {data && <Link href={href({ date: data.today })} className="btn small secondary">Today</Link>}
          <Link href={href({ date: stepDate(view, date, 1) })} className="btn small secondary">Next {view}</Link>
        </div>
      </nav>
      {data === null ? (
        <div role="alert" style={{ marginTop: 12 }}>
          <p className="form-error">Unable to load the calendar.</p>
          <Link href={href({})} className="btn secondary small">Try again</Link>
        </div>
      ) : (
        <>
          {data.truncated && <p className="muted" role="status">Some items are not shown.</p>}
          {overlapping > 0 && (
            <p className="form-warning" role="note" style={{ marginTop: 12 }}>
              {overlapping === 1 ? "1 item overlaps" : `${overlapping} items overlap`} with another plan for the same person. Check the items marked “Overlap”.
            </p>
          )}
          {data.items.length === 0 && <p className="empty" role="status">Nothing planned this {view}.</p>}
          {shown.map(([day, items]) => renderDay(data, day, items))}
        </>
      )}
    </div>
  );
}

import Link from "next/link";

import {
  calendarQuery, CAMPUS_CALENDAR_URL, type CampusCalendarData, type CampusItem, type CampusSummary, DRIVE_STATUS_LABEL, OUTCOME_LABELS, shiftMonth,
} from "@/lib/campusPlacement";
import { dayText, EVENT_KIND_LABEL } from "@/lib/recruiterColleges";

const KIND_LABEL: Record<CampusItem["kind"], string> = { drive: "Campus drive", event: "Placement calendar", batch: "Batch pass-out" };

function detail(item: CampusItem): string {
  if (item.kind === "drive") return [item.code, item.status ? DRIVE_STATUS_LABEL[item.status] ?? item.status : null].filter(Boolean).join(" · ");
  if (item.kind === "event") return EVENT_KIND_LABEL[item.event_kind ?? ""] ?? "Placement calendar";
  return item.student_count !== null ? `${item.student_count.toLocaleString("en-IN")} students` : "";
}

/** pob-015 V10: the TPO partnerships widget (feeds pob-028). */
export function TpoWidget({ summary }: { summary: CampusSummary | null }) {
  if (!summary) return <section className="action-card wide" aria-label="TPO partnerships"><h3>TPO partnerships</h3><p className="form-error">Unable to load the TPO summary.</p></section>;
  const tiles: [string, number | string][] = [
    ["Colleges", summary.colleges], ["Vacancies shared (30 days)", summary.shared_30d], ["Awaiting a reply", summary.awaiting],
    ["Campus dates (next 30 days)", summary.upcoming_truncated ? `${summary.upcoming_30d}+` : summary.upcoming_30d],
    ...OUTCOME_LABELS.map(([key, label]): [string, number] => [`Students: ${label.toLowerCase()}`, summary.outcomes[key]]),
  ];
  return (
    <section className="action-card wide" aria-labelledby="tpo-widget-title">
      <h3 id="tpo-widget-title">TPO partnerships</h3>
      <ul style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 12, listStyle: "none", padding: 0, margin: 0 }}>
        {tiles.map(([label, value]) => (
          <li key={label}><strong style={{ fontSize: 22, display: "block" }}>{value}</strong><span className="muted">{label}</span></li>
        ))}
      </ul>
    </section>
  );
}

// pob-015 (DEC-SCOPE-426 V8/V9): drives, placement calendar entries and batch pass-outs of the caller's colleges for one month, by date.
// Server-rendered; the month links change ?month=. `data` null = the read failed.
export default function CampusCalendar({ data, month, basePath, collegePath }: {
  data: CampusCalendarData | null; month: string; basePath: string; collegePath: (orgId: string) => string;
}) {
  const range = data ? { from: data.from, to: data.to } : null;
  const title = new Date(`${month}-01T00:00:00Z`).toLocaleDateString("en-IN", { month: "long", year: "numeric", timeZone: "UTC" });
  const days = data ? [...new Set(data.items.map((i) => i.date))] : [];
  return (
    <section className="action-card wide" aria-labelledby="campus-calendar-title">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id="campus-calendar-title" style={{ margin: 0 }}>{title}</h3>
        <nav aria-label="Month" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <Link className="btn secondary small" href={`${basePath}?month=${shiftMonth(month, -1)}`}>← Previous month</Link>
          <Link className="btn secondary small" href={`${basePath}?month=${shiftMonth(month, 1)}`}>Next month →</Link>
          {range && <a className="btn ghost small" href={`${CAMPUS_CALENDAR_URL}.ics?${calendarQuery(range)}`} download>Download calendar (.ics)</a>}
        </nav>
      </div>
      {!data ? <p className="form-error">Unable to load the campus calendar. Please reload the page.</p> : data.items.length === 0 ? (
        <p className="empty">No campus drives, placement calendar entries or batch pass-outs this month.</p>
      ) : (
        <>
          {days.map((day) => (
            <div key={day} style={{ marginTop: 12 }}>
              <h4 style={{ margin: "0 0 4px" }}>{dayText(day)}</h4>
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {data.items.filter((i) => i.date === day).map((i) => (
                  <li key={`${i.kind}-${i.id}`} style={{ borderTop: "1px solid var(--line, #e5e7eb)", padding: "6px 0", overflowWrap: "anywhere" }}>
                    <span className="badge">{KIND_LABEL[i.kind]}</span> <strong>{i.title}</strong>
                    {i.end_date && i.end_date !== i.date && <> · until {dayText(i.end_date)}</>}
                    {detail(i) && <> · {detail(i)}</>}
                    <div><Link href={collegePath(i.college.id)}>{i.college.name}</Link> <span className="muted">({i.college.code})</span></div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {data.truncated && <p className="muted">Showing the first {data.items.length} entries.</p>}
        </>
      )}
    </section>
  );
}

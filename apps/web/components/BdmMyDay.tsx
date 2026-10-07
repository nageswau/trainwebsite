import Link from "next/link";

import { BDM_TYPE_LABEL, type BdmType } from "@/lib/bdm";
import { STATUS_CLASS, STATUS_LABEL, type AppointmentStatus } from "@/lib/bdmAppointments";
import { followUpText, type MyDay, timeText, tripAppointmentsText, tripDateText } from "@/lib/bdmMyDay";
import { LINK_STYLE } from "@/lib/bdmOrganizations";

// bdm-014 (DEC-SCOPE-096 §6): My Day -- the §15 common section, then the type's "Today's overview" tiles. A plain function of its
// data (no client state); the sections stack on a phone and sit side by side on wider screens. Untracked tiles say so in words, as
// SchoolKpiBoard does -- never a fabricated 0 (AC3).
const SECTIONS = { display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))", marginBottom: 16 } as const;
const LIST = { listStyle: "none", padding: 0, margin: "8px 0 0" } as const;
const ROW = { display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", padding: "8px 0", borderTop: "1px solid var(--line, #e5e7eb)" } as const;
const LINK = { ...LINK_STYLE, overflowWrap: "anywhere" } as const;
const HEAD = { margin: 0, fontSize: 18 } as const;

function empty(text: string, href: string, action: string) {
  return (
    <div style={{ marginTop: 8 }}>
      <p className="muted" style={{ margin: "0 0 8px" }}>{text}</p>
      <Link href={href} className="btn secondary small">{action}</Link>
    </div>
  );
}

export default function BdmMyDay({ data }: { data: MyDay }) {
  const { appointments, trips, follow_ups: followUps } = data;
  const typeLabel = BDM_TYPE_LABEL[data.bdm_type as BdmType] ?? data.bdm_type;
  return (
    <>
      <div style={SECTIONS}>
        <section className="panel" aria-labelledby="my-day-appointments">
          <h3 id="my-day-appointments" style={HEAD}>Today&apos;s appointments: {appointments.count}</h3>
          {appointments.items.length === 0 ? (
            empty("No appointments today.", "/bdm/appointments/new", "Book an appointment")
          ) : (
            <ul style={LIST}>
              {appointments.items.map((a) => (
                <li key={a.id} style={ROW}>
                  <Link href={`/bdm/appointments/${a.id}`} style={LINK}>{timeText(a.starts_at)} — {a.organization.name}</Link>
                  {a.status !== "scheduled" && (
                    <span className={STATUS_CLASS[a.status as AppointmentStatus] ?? "status"}>{STATUS_LABEL[a.status as AppointmentStatus] ?? a.status}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {appointments.truncated && (
            <p className="muted" role="status">Showing the first {appointments.items.length} of {appointments.count} appointments. <Link href="/bdm/calendar?view=day" style={LINK}>Open the calendar</Link></p>
          )}
        </section>

        <section className="panel" aria-labelledby="my-day-travel">
          <h3 id="my-day-travel" style={HEAD}>Upcoming travel</h3>
          {trips.items.length === 0 ? (
            empty("No upcoming travel.", "/bdm/travel/new", "Plan a trip")
          ) : (
            <>
              <ul style={LIST}>
                {trips.items.map((t) => (
                  <li key={t.id} style={{ ...ROW, display: "block" }}>
                    <Link href={`/bdm/travel/${t.id}`} style={LINK}>{tripDateText(t.travel_date)} — {t.from_place} → {t.to_place}</Link>
                    <div className="muted">{tripAppointmentsText(t.appointment_count)}</div>
                  </li>
                ))}
              </ul>
              <Link href="/bdm/travel" style={LINK}>All travel ({trips.total})</Link>
            </>
          )}
        </section>

        <section className="panel" aria-labelledby="my-day-follow-ups">
          <h3 id="my-day-follow-ups" style={HEAD}>Follow-ups</h3>
          <p className="muted" style={{ margin: "4px 0 0" }}>Due today or overdue.</p>
          {followUps.groups.length === 0 ? (
            empty("No follow-ups due.", "/bdm/follow-ups", "View follow-ups")
          ) : (
            <>
              <ul style={LIST}>
                {followUps.groups.map((g) => <li key={g.key} style={ROW}>{followUpText(g)}</li>)}
              </ul>
              <Link href="/bdm/follow-ups" style={LINK}>View follow-ups</Link>
            </>
          )}
        </section>
      </div>

      <section className="card" aria-labelledby="my-day-overview">
        <h3 id="my-day-overview" style={HEAD}>{typeLabel} overview</h3>
        <p className="muted" style={{ margin: "4px 0 0" }}>Today, from your own records.</p>
        <dl className="kpi-grid">
          {data.tiles.map((k) => (
            <div className="kpi-tile" key={k.key}>
              <dt>{k.label}</dt>
              {k.tracked && k.value !== null ? (
                <dd className="kpi-value">{k.value.toLocaleString("en-IN")}</dd>
              ) : (
                <dd>
                  <span className="badge">Not tracked yet</span>
                  {k.note && <span className="kpi-note muted">{k.note}</span>}
                </dd>
              )}
            </div>
          ))}
        </dl>
      </section>
    </>
  );
}

import { type AppointmentEvent, STATUS_LABEL } from "@/lib/bdmAppointments";
import { formatSchoolDateTime } from "@/lib/formatDate";

// bdm-006 (AC3, AC4): every transition in order, with who, when, the old and new time of a reschedule and any reason. Uses the existing
// journey-timeline styles (.jtl). Plain text only (R-F12).
export default function BdmAppointmentHistory({ events }: { events: AppointmentEvent[] }) {
  return (
    <section className="action-card wide" aria-label="History">
      <h3>History</h3>
      <ol className="jtl" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {events.map((e, i) => (
          <li key={`${e.created_at}-${i}`} className="jtl-row">
            <div className="jtl-rail" aria-hidden="true">
              <span className="jtl-node" />
            </div>
            <div>
              <span className="jtl-date">{formatSchoolDateTime(e.created_at, true)}</span>
              <p className="jtl-title">{e.from_status ? `${STATUS_LABEL[e.from_status]} → ${STATUS_LABEL[e.to_status]}` : "Booked"}</p>
              <p className="jtl-detail">
                By {e.actor_name}
                {e.old_starts_at && e.new_starts_at && ` · moved from ${formatSchoolDateTime(e.old_starts_at, true)} to ${formatSchoolDateTime(e.new_starts_at, true)}`}
              </p>
              {e.reason && <p className="jtl-detail">Reason: {e.reason}</p>}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

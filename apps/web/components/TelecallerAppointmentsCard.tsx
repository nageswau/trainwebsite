import Link from "next/link";

import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { APPOINTMENT_KIND, type DashboardAppointment } from "@/lib/telecallerMetrics";

// tel-021 (Appendix B B5): my counselling bookings and accepted BDM meetings scheduled today, by time. `null` = the read failed.
export default function TelecallerAppointmentsCard({ appointments }: { appointments: DashboardAppointment[] | null }) {
  return (
    <section className="card" aria-labelledby="my-appointments-title" style={{ marginTop: 16 }}>
      <h3 id="my-appointments-title">Today&apos;s appointments</h3>
      {appointments === null ? (
        <p className="muted" role="status">Appointments are unavailable right now.</p>
      ) : appointments.length === 0 ? (
        <p className="muted">No appointments today.</p>
      ) : (
        <ul aria-label="Today's appointments" style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>
          {appointments.map((a) => (
            <li key={`${a.kind}-${a.id}`}>
              {formatSchoolDateTime(a.scheduled_at, true)} · {APPOINTMENT_KIND[a.kind]} · {a.lead_id ? (
                <Link href={`/telecaller/leads/${encodeURIComponent(a.lead_id)}`} style={LINK_STYLE}>{a.title}</Link>
              ) : a.title} · {a.code}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

import Link from "next/link";

import { STATUS_LABEL, TYPE_LABEL } from "@/lib/bdmAppointments";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { appointmentPagePath, itineraryWhen, type Trip } from "@/lib/bdmTravel";

// bdm-011 (EVID-016 §4, Agent §D, School §F): the trip's linked appointments -- time, organization, meeting, status -- shared by
// the trip page and the travel report. Statuses are words (F9). The note says why the list may not happen as planned: the trip is
// not approved yet (Q-05: linked appointments stay and say so) or was cancelled (L4: links stay as the record).
export default function TripItinerary({ trip, view }: { trip: Trip; view: "owner" | "manager" }) {
  const multiDay = trip.return_date !== trip.travel_date;
  const note = trip.itinerary.length === 0 ? null : trip.travel_status === "cancelled"
    ? "This trip is cancelled. Its appointments stay listed for the record; reschedule or cancel them on each appointment."
    : trip.approval_status !== "approved" ? "Trip not approved yet — these appointments depend on the manager's approval." : null;
  return (
    <>
      {note && <p className="form-warning" role="note" style={{ marginTop: 0 }}>{note}</p>}
      {trip.itinerary.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>
          No appointments are linked to this trip yet.
          {view === "owner" && <> Link one from an appointment&apos;s Edit form, or <Link href="/bdm/appointments/new">Book an appointment</Link>.</>}
        </p>
      ) : (
        <div className="table-wrap" role="region" aria-label="Appointments on this trip" tabIndex={0}>
          {/* QA11-02: on phones each row is a labelled card (globals.css .trip-itinerary), so the status is never behind a scroll */}
          <table className="table trip-itinerary">
            <caption className="visually-hidden">Appointments on this trip</caption>
            <thead>
              <tr><th scope="col">Time</th><th scope="col">Organization</th><th scope="col">Meeting</th><th scope="col">Status</th></tr>
            </thead>
            <tbody>
              {trip.itinerary.map((a) => (
                <tr key={a.id}>
                  <td data-label="Time" style={{ whiteSpace: "nowrap" }}>{itineraryWhen(a.starts_at, multiDay)}</td>
                  <td data-label="Organization"><Link href={appointmentPagePath(view, a.id)} style={LINK_STYLE}>{a.organization.name}</Link></td>
                  <td data-label="Meeting">{TYPE_LABEL[a.appointment_type] ?? a.appointment_type}</td>
                  <td data-label="Status">{STATUS_LABEL[a.status]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

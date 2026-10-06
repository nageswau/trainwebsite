import type { AppointmentTrip } from "@/lib/bdmAppointments";
import { TRAVEL_LABEL, type TripRow } from "@/lib/bdmTravel";
import { formatCalendarDate } from "@/lib/formatDate";

// bdm-011 (DEC-SCOPE-090 L2): the optional trip an appointment belongs to. Presentational: the form owns the value. The choices are
// the BDM's open trips (read once by the page) that cover the appointment's IST date; the API decides. A current trip that can no
// longer take appointments (cancelled, completed) stays listed so the select never hides the stored value -- and can be unlinked.
type TripLike = Pick<TripRow, "id" | "code" | "from_place" | "to_place" | "travel_date" | "return_date" | "travel_status">;

export const covers = (t: Pick<TripRow, "travel_date" | "return_date">, day: string) => day !== "" && t.travel_date <= day && day <= t.return_date;

const label = (t: TripLike, closed: boolean) =>
  `${t.code} · ${t.from_place} → ${t.to_place} (${formatCalendarDate(t.travel_date)} – ${formatCalendarDate(t.return_date)})${closed ? ` — ${TRAVEL_LABEL[t.travel_status]}` : ""}`;

export default function BdmAppointmentTripField({ trips, current, day, value, onChange, unavailable = false }: {
  trips: TripRow[]; current: AppointmentTrip | null; day: string; value: string; onChange: (id: string) => void; unavailable?: boolean;
}) {
  const choices: [TripLike, boolean][] = trips.filter((t) => covers(t, day)).map((t) => [t, false]);
  if (current && !choices.some(([t]) => t.id === current.id)) choices.unshift([current, current.travel_status === "cancelled" || current.travel_status === "completed"]);
  const hint = unavailable ? "Your trips couldn't be loaded — you can link this appointment to a trip later."
    : day === "" ? "Choose the date first."
    : choices.length === 0 ? "None of your open trips covers this date." : null;
  return (
    <fieldset className="form-section">
      <legend>Travel</legend>
      <div className="field">
        <label htmlFor="appt-trip">Trip</label>
        <select id="appt-trip" value={value} disabled={day === "" || (unavailable && !current)} aria-describedby={hint ? "appt-trip-hint" : undefined}
          onChange={(e) => onChange(e.target.value)}>
          <option value="">No trip</option>
          {choices.map(([t, closed]) => <option key={t.id} value={t.id}>{label(t, closed)}</option>)}
        </select>
        {hint && <p id="appt-trip-hint" className="muted" style={{ margin: 0 }}>{hint}</p>}
      </div>
    </fieldset>
  );
}

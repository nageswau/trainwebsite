import { APPROVAL_LABEL, MODE_LABEL, TRAVEL_LABEL, type Trip } from "@/lib/bdmTravel";
import { formatCalendarDate, formatDate } from "@/lib/formatDate";

// bdm-010 (§12.2 F2): the trip's §3 fields as a definition list, shared by the BDM's and the manager's trip pages. Multi-line
// text keeps its line breaks as text (pre-wrap), never as HTML (S6). Organization and appointment time arrive with bdm-011.
export default function TripDetails({ trip }: { trip: Trip }) {
  const rows: [string, React.ReactNode][] = [
    ["Travel ID", trip.code],
    ["BDM", trip.bdm.full_name],
    ["Travel date", formatCalendarDate(trip.travel_date)],
    ["Return date", formatCalendarDate(trip.return_date)],
    ["From", trip.from_place],
    ["To", trip.to_place],
    ["Mode of travel", MODE_LABEL[trip.mode]],
    ["Accommodation required", trip.accommodation_required ? "Yes" : "No"],
    ["Purpose", <span key="p" style={{ whiteSpace: "pre-wrap" }}>{trip.purpose}</span>],
    ["Approval status", APPROVAL_LABEL[trip.approval_status]],
    ["Travel status", TRAVEL_LABEL[trip.travel_status]],
  ];
  if (trip.decided_by) rows.push([trip.approval_status === "rejected" ? "Rejected by" : "Approved by", `${trip.decided_by.full_name}, ${formatDate(trip.decided_at)}`]);
  if (trip.completed_at) rows.push(["Completed", formatDate(trip.completed_at)]);
  if (trip.cancelled_at) rows.push(["Cancelled", formatDate(trip.cancelled_at)]);
  return (
    <dl className="form-grid" style={{ margin: 0 }}>
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt className="muted" style={{ fontSize: 13 }}>{label}</dt>
          <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

import { APPROVAL_LABEL, TRAVEL_LABEL, type TripRow } from "@/lib/bdmTravel";

// bdm-010 (F9): a trip's two statuses as words, never colour alone -- the list row and the trip page header.
export default function TripStatusBadges({ trip }: { trip: Pick<TripRow, "approval_status" | "travel_status"> }) {
  return (
    <>
      <span className="badge state-badge">Approval: {APPROVAL_LABEL[trip.approval_status]}</span>{" "}
      <span className="badge state-badge">Travel: {TRAVEL_LABEL[trip.travel_status]}</span>
    </>
  );
}

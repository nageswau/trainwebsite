import type { Joining, RecOffer } from "@/lib/recruiterOffers";

/** rec-022: one offer as the API returns it (Offer Pending, no letter, the writer's view). */
export const recOffer = (over: Partial<RecOffer> = {}): RecOffer => ({
  id: "O1", status: "offer_pending", status_label: "Offer Pending", position: "Java Developer", compensation: "600000.00", currency: "INR",
  offered_on: "2026-10-09", joining_date: "2026-11-02", letter: null, letter_url: null,
  application: { id: "A1", status: "selected", status_label: "Selected" }, candidate: { id: "C1", code: "CAN-000001", name: "Rahul Kumar" },
  requirement: { id: "J1", code: "REQ-000001", title: "Java Developer" }, company: { id: "CO1", name: "Acme Technologies" },
  history: [{ event: "created", from_status: null, to_status: "offer_pending", fields: null, note: null, actor: { id: "r1", full_name: "Riya Recruiter" },
    created_at: "2026-10-09T05:30:00Z" }],
  allowed_statuses: [{ key: "offer_received", label: "Offer Received" }, { key: "accepted", label: "Accepted" }, { key: "declined", label: "Declined" }],
  can_edit: true, can_upload: true, joining: null,
  ...over,
});

/** rec-023: a pending joining as the API returns it for an Accepted offer (the writer's view). */
export const recJoining = (over: Partial<Joining> = {}): Joining => ({
  status: "pending", status_label: "Pending", expected_joining_date: "2026-11-02", actual_joining_date: null, location: null, reporting_manager: null,
  confirmed_by: null, confirmed_on: null, reason: null, proof: null, overdue: false,
  allowed_statuses: [{ key: "joined", label: "Joined" }, { key: "did_not_join", label: "Did Not Join" }], can_edit: true, can_upload_proof: true,
  ...over,
});

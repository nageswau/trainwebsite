import type { Visit } from "@/lib/visits";

// upc-010: one visit, every permission off, to be overridden per test.
export const visit = (over: Partial<Visit> = {}): Visit => ({
  id: "v1", code: "VIS-000001",
  university: { id: "u1", name: "ABC University", university_code: "UNV-000001", city: "London", country: { id: "gb", name: "United Kingdom" } },
  city: "London", lead: { id: "pm", full_name: "Rahul Partnerships", active: true }, proposed_date: "2030-01-10", confirmed_date: null,
  status: "planned", approval_state: "draft", submitted_at: null, purpose: "Discuss the MoU", created_by: { id: "pm", full_name: "Rahul Partnerships", active: true },
  travel_required: true, travel_notes: "Flight DEL-LHR", hotel_required: false, hotel_notes: null, agenda: "MoU", expected_outcome: "Signed draft",
  follow_up_date: null, rejection_reason: null, decided_by: null, decided_at: null, close_reason: null, participants: [], contacts: [], events: [],
  permissions: { can_edit: false, can_submit: false, can_decide: false, can_book: false, can_complete: false, can_follow_up: false, can_close: false },
  editable_fields: [], created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-01T00:00:00Z",
  ...over,
});

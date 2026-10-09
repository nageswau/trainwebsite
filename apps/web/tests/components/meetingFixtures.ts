import type { Meeting } from "@/lib/meetings";

const person = (id: string, full_name: string) => ({ id, full_name, active: true });

// upc-009: one scheduled meeting as the API returns it; tests override what they exercise.
export function meeting(overrides: Partial<Meeting> = {}): Meeting {
  return {
    id: "m1", code: "UMT-000001", meeting_type: "mou_discussion", starts_at: "2030-01-10T04:30:00Z", mode: "offline", status: "scheduled",
    university: { id: "u1", name: "ABC University", university_code: "UNV-000001", city: "London", country: { id: "c1", name: "United Kingdom" } },
    responsible: person("p1", "Rahul"), contact: { id: "k1", name: "Priya Raman", designation: "Director" }, warnings: [],
    location: "Main campus", meeting_url: null, agenda: "MoU clauses", notes: null, discussion_points: null, decisions: null, next_action: null,
    next_action_due_on: null, next_meeting_date: null, created_by: person("p1", "Rahul"), completed_by: null, completed_at: null, cancelled_at: null,
    cancel_reason: null, participants: { contacts: [{ id: "k1", name: "Priya Raman", designation: "Director" }], employees: [] }, events: [],
    follow_ups: [], permissions: { can_edit: false, can_complete: false, can_cancel: false }, created_at: "2030-01-01T00:00:00Z",
    updated_at: "2030-01-01T00:00:00Z",
    ...overrides,
  };
}

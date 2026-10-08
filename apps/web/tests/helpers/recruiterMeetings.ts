import type { RecMeeting } from "@/lib/recruiterMeetings";

// rec-028: one recruiter meeting as the API returns it, for the component tests.
export const recMeeting = (over: Partial<RecMeeting> = {}): RecMeeting => ({
  id: "M1", code: "MTG-000007", meeting_type: "contract_discussion", starts_at: "2026-10-09T05:30:00Z", mode: "Online", location: null,
  meeting_url: "https://meet.example.com/abc", purpose: "Fee per hire", status: "scheduled", outcome: null, next_action: null,
  company: { id: "C1", code: "CMP-000042", name: "Acme Technologies", assigned_recruiter: { id: "r1", full_name: "Riya Recruiter" } },
  contact: { id: "K1", name: "Priya HR" }, participants: { contacts: [{ id: "K1", name: "Priya HR" }], recruiters: [] },
  history: [{ event: "scheduled", old_starts_at: null, new_starts_at: "2026-10-09T05:30:00Z", reason: null, actor: { id: "r1", full_name: "Riya Recruiter" }, created_at: "2026-10-08T05:00:00Z" }],
  follow_up: null, created_by: { id: "r1", full_name: "Riya Recruiter" }, created_at: "2026-10-08T05:00:00Z", completed_at: null, completed_by: null,
  cancelled_at: null, cancel_reason: null, can_change: true, can_record_outcome: false, ...over,
});

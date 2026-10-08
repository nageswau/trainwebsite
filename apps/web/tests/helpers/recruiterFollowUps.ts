import type { RecFollowUp } from "@/lib/recruiterFollowUps";

// rec-024: one recruiter follow-up as the API returns it, for the component tests.
export const recFollowUp = (over: Partial<RecFollowUp> = {}): RecFollowUp => ({
  id: "F1", reason: "jd", due_at: "2026-10-09T05:30:00Z", notes: "Ask for the Java JD", status: "open", outcome: null, overdue: false,
  company: { id: "C1", code: "CMP-000042", name: "Acme Technologies", assigned_recruiter: { id: "r1", full_name: "Riya Recruiter" } },
  contact: { id: "K1", name: "Priya HR" }, requirement: null, application_id: null, created_by: { id: "r1", full_name: "Riya Recruiter" },
  created_at: "2026-10-08T05:00:00Z", completed_at: null, completed_by: null, cancelled_at: null, cancel_reason: null, can_change: true, ...over,
});

import type { RecInterview } from "@/lib/recruiterInterviews";

/** rec-020: one interview as the API returns it (an HR round, scheduled, the writer's view). */
export const recInterview = (over: Partial<RecInterview> = {}): RecInterview => ({
  id: "I1", code: "INT-000001", round: "hr_round", round_label: "HR Round", scheduled_at: "2026-10-12T05:30:00Z", mode: "Online",
  meeting_url: "https://meet.example.com/abc", interviewer: "Meera (HR)", location: null, status: "scheduled", status_label: "Scheduled", result: null,
  application: { id: "A1", status: "interview", status_label: "Interview" }, candidate: { id: "C1", code: "CAN-000001", name: "Rahul Kumar" },
  requirement: { id: "J1", code: "REQ-000001", title: "Java Developer" }, company: { id: "CO1", name: "Acme Technologies" }, contact: null,
  history: [{ event: "scheduled", from_status: null, to_status: "scheduled", old_scheduled_at: null, new_scheduled_at: "2026-10-12T05:30:00Z", note: null,
    actor: { id: "r1", full_name: "Riya Recruiter" }, created_at: "2026-10-09T05:30:00Z" }],
  allowed_statuses: [{ key: "confirmed", label: "Confirmed" }, { key: "on_hold", label: "On Hold" }], can_edit: true, can_reschedule: true,
  feedback: null, can_feedback: false, updated_at: "2026-10-09T05:30:00.123456+00:00",
  // hrc-028 (DEC-SCOPE-398 I1/I3)
  round_number: null, ends_at: null, time_zone: "Asia/Kolkata", local_when: "12 Oct 2026, 11:00 AM IST (UTC+05:30)", platform: null, platform_label: null,
  phone_details: null, instructions: null, documents_required: null, cancel_reason: null, can_cancel: true,
  ...over,
});

import type { FollowUp } from "@/lib/telecallerFollowUps";

// tel-011: one follow-up as the API returns it, for the component tests.
export const followUp = (over: Partial<FollowUp> = {}): FollowUp => ({
  id: "F1", due_at: "2026-10-08T10:30:00Z", reason: "fee_details", notes: "Send the fee sheet", next_action: "Call at 4 PM", status: "open",
  overdue: false, lead: { id: "L1", lead_code: "LD-000042", name: "Rahul", priority: "hot", status: "contacted", status_label: "Contacted",
    product: { id: "p1", name: "Cyber Security" }, telecaller: { id: "t1", full_name: "Tara Caller" } },
  created_by: { id: "t1", full_name: "Tara Caller" }, created_at: "2026-10-06T05:00:00Z", completed_at: null, completed_by: null, cancelled_at: null,
  cancel_reason: null, can_change: true, ...over,
});

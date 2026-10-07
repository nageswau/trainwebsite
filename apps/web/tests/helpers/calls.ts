import type { LeadCall } from "@/lib/telecallerCalls";

// tel-010: one call as the API returns it, for the component tests.
export const call = (over: Partial<LeadCall> = {}): LeadCall => ({
  id: "C1", lead_id: "L1", occurred_at: "2026-10-07T05:30:00Z", duration_seconds: 245, call_type: "outgoing", outcome: "need_information",
  outcome_label: "Connected – Need Information", connected: true, remarks: "Wants the fee sheet", caller: { id: "t1", full_name: "Tara Caller" },
  created_at: "2026-10-07T05:31:00Z", can_change: true, ...over,
});

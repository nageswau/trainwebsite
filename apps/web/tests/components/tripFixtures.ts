// bdm-010 test fixtures: one trip in any state, and fetch responses.
import type { Trip, TripRow } from "@/lib/bdmTravel";

export const row = (over: Partial<TripRow> = {}): TripRow => ({
  id: "t1", code: "TRV-000001", bdm: { id: "b1", full_name: "Asha" }, travel_date: "2026-10-10", return_date: "2026-10-11",
  from_place: "Hyderabad", to_place: "Vijayawada", mode: "train", accommodation_required: false, estimated_cost: "2500.00",
  actual_cost: "0.00", currency: "INR", approval_status: "draft", travel_status: "planned", submitted_at: null, ...over,
});

export const metrics = (over: Partial<Trip["metrics"]> = {}): Trip["metrics"] => ({
  meetings_planned: 0, meetings_completed: 0, estimated_cost: "2500.00", actual_cost: "0.00", cost_per_completed_meeting: null,
  expected_leads: null, expected_revenue: null, actual_leads: 0, actual_revenue: null, ...over,
});

export const trip = (over: Partial<Trip> = {}): Trip => ({
  ...row(), itinerary: [], metrics: metrics(), purpose: "College visits", remarks: null, rejection_reason: null, decided_by: null, decided_at: null, completed_at: null,
  cancelled_at: null, expenses: [], can_edit: false, can_submit: false, can_withdraw: false, can_start: false, can_complete: false,
  can_cancel: false, can_add_expense: false, can_decide: false, ...over,
});

export const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

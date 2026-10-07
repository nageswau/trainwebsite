// tel-011 (DEC-SCOPE-094): follow-ups on a lead -- types, the EVID-019 §7 reason labels and the endpoints. The API decides scope, every
// rule and `can_change` (only the lead's telecaller, on an open follow-up of a lead not handed over); the UI only offers what it allows.
import { isPage, type Page } from "@/lib/apiErrors";
import { personTargets } from "@/lib/leadStages";
import { leadUrl, type PersonRef, type Priority } from "@/lib/telecallerLeads";

export const REASONS = [
  { key: "discuss_with_parents", label: "Need to discuss with parents" },
  { key: "course_details", label: "Need course details" },
  { key: "fee_details", label: "Need fee details" },
  { key: "waiting_salary", label: "Waiting for salary" },
  { key: "waiting_documents", label: "Waiting for documents" },
  { key: "comparing_courses", label: "Comparing courses" },
  { key: "next_month", label: "Interested next month" },
  { key: "next_intake", label: "Interested next intake" },
  { key: "university_information", label: "Waiting for university information" },
  { key: "counselor_call", label: "Requested counselor call" },
] as const;
export type FollowUpReason = (typeof REASONS)[number]["key"];
export const REASON_LABEL: Record<string, string> = Object.fromEntries(REASONS.map((r) => [r.key, r.label]));
export const reasonLabel = (key: string) => REASON_LABEL[key] ?? key;
export const NOTES_MAX = 2000;
export const ACTION_MAX = 200;

export type FollowUp = {
  id: string; due_at: string; reason: FollowUpReason; notes: string | null; next_action: string | null; status: "open" | "done" | "cancelled";
  overdue: boolean;
  lead: { id: string; lead_code: string; name: string; priority: Priority; status: string; status_label: string; product: { id: string; name: string } | null;
    telecaller: PersonRef | null; last_call?: { occurred_at: string; outcome: string } | null }; // tel-010 D10 (F8): the §7 "Last Call"
  created_by: PersonRef; created_at: string; completed_at: string | null; completed_by: PersonRef | null; cancelled_at: string | null;
  cancel_reason: string | null; can_change: boolean;
};
export type View = "day" | "overdue";
export type FollowUpPage = Page<FollowUp> & { day: string; counts: Record<View, number> };

export const FOLLOW_UPS_URL = "/api/v1/telecaller/follow-ups";
export const LIST_LIMIT = 50;
export const followUpUrl = (id: string, action?: "complete" | "cancel") => `${FOLLOW_UPS_URL}/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;
export const leadFollowUpsUrl = (leadId: string) => leadUrl(leadId, `/follow-ups?limit=${LIST_LIMIT}`);
export const createFollowUpUrl = (leadId: string) => leadUrl(leadId, "/follow-ups");

export function followUpsUrl(view: View, day: string | null, offset = 0): string {
  const query = new URLSearchParams({ view, limit: String(LIST_LIMIT), offset: String(offset) });
  if (view === "day" && day) query.set("day", day);
  return `${FOLLOW_UPS_URL}?${query}`;
}

export function isFollowUp(data: unknown): data is FollowUp {
  const d = data as Partial<FollowUp> | null;
  return !!d && typeof d.id === "string" && typeof d.due_at === "string" && !!d.lead && typeof d.can_change === "boolean";
}

export function isFollowUpPage(data: unknown): data is FollowUpPage {
  return isPage(data) && typeof (data as { day?: unknown }).day === "string" && !!(data as { counts?: unknown }).counts;
}

/** F5: "Also move the lead to Follow-up" is offered only where tel-004 lets a telecaller make that move. */
export const canMoveToFollowUp = (stage: string) => personTargets(stage, false).includes("follow_up");

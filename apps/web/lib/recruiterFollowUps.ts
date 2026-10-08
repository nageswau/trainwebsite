// rec-024 (DEC-SCOPE-131): recruiter follow-ups -- types, the EVID-018 §18 reason labels and the endpoints. The API decides scope, every
// rule and `can_change` (the company's assigned recruiter or super admin, on an open follow-up of an active company); the UI only offers
// what it allows.
import { isPage, type Page } from "@/lib/apiErrors";
import { COMPANIES_URL } from "@/lib/recruiterCompanies";

/** EVID-018 §18 (L738-L754), in source order and wording. */
export const REASONS = [
  { key: "new_requirement", label: "Follow-up for new requirement" },
  { key: "jd", label: "Follow-up for JD" },
  { key: "profile_feedback", label: "Follow-up for profile feedback" },
  { key: "interview_feedback", label: "Interview feedback" },
  { key: "offer_status", label: "Offer status" },
  { key: "joining_confirmation", label: "Joining confirmation" },
  { key: "new_openings", label: "New openings" },
  { key: "contract_mou", label: "Contract/MoU" },
  { key: "payment_commercial", label: "Payment/commercial discussion" },
] as const;
export type FollowUpReason = (typeof REASONS)[number]["key"];
const REASON_LABEL: Record<string, string> = Object.fromEntries(REASONS.map((r) => [r.key, r.label]));
export const reasonLabel = (key: string) => REASON_LABEL[key] ?? key;
export const NOTES_MAX = 2000;
export const OUTCOME_MAX = 500;

type PersonRef = { id: string; full_name: string };
export type RecFollowUp = {
  id: string; reason: FollowUpReason; due_at: string; notes: string | null; status: "open" | "done" | "cancelled"; outcome: string | null;
  overdue: boolean; company: { id: string; code: string; name: string; assigned_recruiter: PersonRef | null };
  contact: { id: string; name: string } | null; requirement: { id: string; title: string } | null; application_id: string | null;
  created_by: PersonRef; created_at: string; completed_at: string | null; completed_by: PersonRef | null; cancelled_at: string | null;
  cancel_reason: string | null; can_change: boolean;
};
export type Due = "today" | "overdue" | "upcoming";
export const DUE_TABS: [Due, string][] = [["today", "Today"], ["overdue", "Overdue"], ["upcoming", "Upcoming"]];
export type FollowUpListPage = Page<RecFollowUp> & { day: string; counts: Record<Due, number> };

export const FOLLOW_UPS_URL = "/api/v1/recruiter/follow-ups";
export const FOLLOW_UPS_PATH = "/recruiter/follow-ups";
export const LIST_LIMIT = 50;
export const followUpUrl = (id: string, action?: "complete" | "cancel") => `${FOLLOW_UPS_URL}/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;
export const companyFollowUpsUrl = (companyId: string) => `${COMPANIES_URL}/${encodeURIComponent(companyId)}/follow-ups`;

export function followUpsUrl(due: Due, offset = 0): string {
  return `${FOLLOW_UPS_URL}?${new URLSearchParams({ due, limit: String(LIST_LIMIT), offset: String(offset) })}`;
}

export function isRecFollowUp(data: unknown): data is RecFollowUp {
  const d = data as Partial<RecFollowUp> | null;
  return !!d && typeof d.id === "string" && typeof d.due_at === "string" && !!d.company && typeof d.can_change === "boolean";
}

export function isFollowUpListPage(data: unknown): data is FollowUpListPage {
  return isPage(data) && typeof (data as { day?: unknown }).day === "string" && !!(data as { counts?: unknown }).counts;
}

// rec-028 (DEC-SCOPE-132): recruiter meetings with a company -- types, the EVID-018 §20 type labels, the views and the endpoints. The API
// decides scope, every rule, `can_change` (the company's assigned recruiter or super admin, on a scheduled meeting of an active company)
// and `can_record_outcome` (the same, once the start has passed); the UI only offers what it allows.
import { isPage, type Page } from "@/lib/apiErrors";
import type { LookupPage } from "@/lib/lookups";
import { COMPANIES_URL } from "@/lib/recruiterCompanies";

/** EVID-018 §20 (L800-L812), in source order and wording. */
export const MEETING_TYPES = [
  { key: "company_meeting", label: "Company meeting" },
  { key: "hr_meeting", label: "HR meeting" },
  { key: "requirement_discussion", label: "Requirement discussion" },
  { key: "recruitment_presentation", label: "Recruitment presentation" },
  { key: "contract_discussion", label: "Contract discussion" },
  { key: "campus_recruitment_discussion", label: "Campus recruitment discussion" },
  { key: "placement_drive_discussion", label: "Placement drive discussion" },
] as const;
export type MeetingType = (typeof MEETING_TYPES)[number]["key"];
const TYPE_LABEL: Record<string, string> = Object.fromEntries(MEETING_TYPES.map((t) => [t.key, t.label]));
export const meetingTypeLabel = (key: string) => TYPE_LABEL[key] ?? key;
export const MODES = ["Online", "Phone", "In person"] as const;
export const PURPOSE_MAX = 1000;
export const OUTCOME_MAX = 2000;
export const NEXT_ACTION_MAX = 500;

type PersonRef = { id: string; full_name: string };
type ContactRef = { id: string; name: string };
export type HistoryEvent = {
  event: "scheduled" | "rescheduled" | "completed" | "cancelled"; old_starts_at: string | null; new_starts_at: string | null;
  reason: string | null; actor: PersonRef; created_at: string;
};
export type RecMeeting = {
  id: string; code: string; meeting_type: MeetingType; starts_at: string; mode: (typeof MODES)[number]; location: string | null;
  meeting_url: string | null; purpose: string | null; status: "scheduled" | "completed" | "cancelled"; outcome: string | null;
  next_action: string | null; company: { id: string; code: string; name: string; assigned_recruiter: PersonRef | null };
  contact: ContactRef | null; participants: { contacts: ContactRef[]; recruiters: PersonRef[] }; history: HistoryEvent[];
  follow_up: { id: string; due_at: string } | null; created_by: PersonRef; created_at: string; completed_at: string | null;
  completed_by: PersonRef | null; cancelled_at: string | null; cancel_reason: string | null; can_change: boolean; can_record_outcome: boolean;
};
export type MeetingView = "upcoming" | "awaiting_outcome" | "completed" | "cancelled";
export const VIEW_TABS: [MeetingView, string][] = [["upcoming", "Upcoming"], ["awaiting_outcome", "Awaiting outcome"], ["completed", "Completed"], ["cancelled", "Cancelled"]];
export type MeetingListPage = Page<RecMeeting> & { counts: Record<MeetingView, number> };

export const MEETINGS_URL = "/api/v1/recruiter/meetings";
export const MEETINGS_PATH = "/recruiter/meetings";
export const LIST_LIMIT = 50;
export const meetingUrl = (id: string, action?: "outcome" | "cancel") => `${MEETINGS_URL}/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;
export const companyMeetingsUrl = (companyId: string) => `${COMPANIES_URL}/${encodeURIComponent(companyId)}/meetings`;

export function meetingsUrl(view: MeetingView, offset = 0): string {
  return `${MEETINGS_URL}?${new URLSearchParams({ view, limit: String(LIST_LIMIT), offset: String(offset) })}`;
}

export const isView = (value: string | null): value is MeetingView => VIEW_TABS.some(([key]) => key === value);

export function isRecMeeting(data: unknown): data is RecMeeting {
  const d = data as Partial<RecMeeting> | null;
  return !!d && typeof d.id === "string" && typeof d.starts_at === "string" && !!d.participants && typeof d.can_change === "boolean";
}

export function isMeetingListPage(data: unknown): data is MeetingListPage {
  return isPage(data) && !!(data as { counts?: unknown }).counts;
}

/** MT5's picker: active placement users (recruiters and managers), names only. */
export async function recruiterOptions(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: "20" });
  if (q) query.set("q", q);
  const response = await fetch(`${MEETINGS_URL}/recruiter-options?${query}`, { signal });
  if (!response.ok) throw new Error(`Recruiter search failed (${response.status})`);
  const page = (await response.json()) as { items: PersonRef[]; total: number };
  return { items: page.items.map((r) => ({ id: r.id, label: r.full_name })), truncated: page.total > page.items.length };
}

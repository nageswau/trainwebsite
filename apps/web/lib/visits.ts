// upc-010 (DEC-SCOPE-124): university visits (§8) -- types, words, URLs and the option searches shared by the visit pages and forms.
import type { LookupPage } from "@/lib/lookups";
import type { ManagerRef } from "@/lib/telecaller";

export const VISIT_STATUSES: Record<string, string> = {
  planned: "Planned", approved: "Approved", travel_booked: "Travel Booked", visit_completed: "Visit Completed", follow_up: "Follow-up", closed: "Closed",
};
// VS2: a planned visit is a draft, waiting for approval, or returned with the head's reason.
export const APPROVAL_STATES: Record<string, string> = { draft: "Draft", waiting: "Waiting for approval", returned: "Returned for changes" };
export const EVENT_ACTIONS: Record<string, string> = {
  create: "Planned", edit: "Edited", submit: "Submitted for approval", approve: "Approved", reject: "Returned", book: "Travel booked",
  complete: "Visit completed", follow_up: "Follow-up started", close: "Closed",
};

export type VisitPermissions = {
  can_edit: boolean; can_submit: boolean; can_decide: boolean; can_book: boolean; can_complete: boolean; can_follow_up: boolean; can_close: boolean;
};
export type VisitUniversity = { id: string; name: string; university_code: string; city: string; country: { id: string; name: string } };
export type VisitRow = {
  id: string; code: string; university: VisitUniversity; city: string; lead: ManagerRef; proposed_date: string; confirmed_date: string | null;
  status: string; approval_state: string | null; submitted_at: string | null;
};
export type VisitEvent = { action: string; from_status: string | null; to_status: string | null; actor: ManagerRef; reason: string | null; created_at: string };
export type Visit = VisitRow & {
  purpose: string; created_by: ManagerRef; travel_required: boolean; travel_notes: string | null; hotel_required: boolean; hotel_notes: string | null;
  agenda: string | null; expected_outcome: string | null; follow_up_date: string | null; rejection_reason: string | null; decided_by: ManagerRef | null;
  decided_at: string | null; close_reason: string | null; participants: ManagerRef[]; contacts: { id: string; name: string; designation: string | null }[];
  events: VisitEvent[]; permissions: VisitPermissions; editable_fields: string[]; created_at: string; updated_at: string;
};

export const VISITS_URL = "/api/v1/partnership/visits";
export const VISITS_PATH = "/partnership/visits";
export const APPROVALS_PATH = `${VISITS_PATH}/approvals`;
export const visitUrl = (id: string, action?: string) => `${VISITS_URL}/${id}${action ? `/${action}` : ""}`;
export const visitPath = (id: string, edit = false) => `${VISITS_PATH}/${id}${edit ? "/edit" : ""}`;
export const newVisitPath = (universityId?: string) => `${VISITS_PATH}/new${universityId ? `?university=${encodeURIComponent(universityId)}` : ""}`;

// VS6/VS7: who may plan and who reads visits (the API decides; this only hides links and skips a read that would be refused).
export const PLANNER_ROLES = new Set(["partnership_manager", "partnership_head"]);
export const VISIT_READERS = new Set([...PLANNER_ROLES, "super_admin"]);

/** "Planned · Waiting for approval", or just the status once it has moved on. */
export const statusText = (v: Pick<VisitRow, "status" | "approval_state">) =>
  [VISIT_STATUSES[v.status] ?? v.status, v.approval_state && APPROVAL_STATES[v.approval_state]].filter(Boolean).join(" · ");

/** A date-only value ("2026-10-18") shown as 18 Oct 2026, without a timezone shift. */
export function dateText(value: string | null | undefined): string {
  if (!value) return "—";
  const [y, m, d] = value.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

/** Today in India (the API's "today", VS10) as YYYY-MM-DD, for date inputs' `min`. */
export const indiaToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

// The list's filters travel in the page URL; only these keys are passed on to the API.
export const VISIT_FILTER_KEYS = ["status", "university_id", "mine"] as const;
export type VisitFilters = Partial<Record<(typeof VISIT_FILTER_KEYS)[number] | "offset", string>>;

function filterParams(filters: VisitFilters): URLSearchParams {
  const query = new URLSearchParams();
  for (const key of VISIT_FILTER_KEYS) {
    const value = filters[key]?.trim();
    if (value) query.set(key, value);
  }
  return query;
}

export function visitListQuery(filters: VisitFilters, limit: number, offset: number): string {
  const query = filterParams(filters);
  query.set("limit", String(limit));
  query.set("offset", String(offset));
  return query.toString();
}

export function visitPageHref(filters: VisitFilters, offset: number, path = VISITS_PATH): string {
  const query = filterParams(filters);
  if (offset > 0) query.set("offset", String(offset));
  const text = query.toString();
  return text ? `${path}?${text}` : path;
}

function optionSearch(kind: "university" | "lead" | "employee") {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: "20" });
    if (q) query.set("q", q);
    const response = await fetch(`${VISITS_URL}/${kind}-options?${query}`, { signal });
    if (!response.ok) throw new Error(`Search failed (${response.status})`);
    const page = (await response.json()) as { items: { id: string; label: string; detail: string | null }[]; total: number };
    return { items: page.items, truncated: page.total > page.items.length };
  };
}
export const universityOptions = optionSearch("university");
export const leadOptions = optionSearch("lead");
export const employeeOptions = optionSearch("employee");

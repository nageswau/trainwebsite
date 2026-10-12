// mgmt-027 (spec MD1-MD14): management discussions & decisions -- types, filters, links and labels. The API decides access (the
// operational tier for discussions; the responsible person for their own decision line) and every rule; this module only shapes
// what the pages send and show.
export const DISCUSSIONS_HOME = "/management/discussions";
export const DISCUSSIONS_API = "/api/v1/management/discussions";
export const MY_DECISIONS_HOME = "/account/management-decisions";
export const MY_DECISIONS_API = "/api/v1/me/management-decisions";
export const DISCUSSIONS_PAGE_SIZE = 25;
export const PENDING_URL = `${DISCUSSIONS_API}?pending=true&limit=10`;

export type DiscussionStatus = "open" | "in_progress" | "completed" | "cancelled";
export type DiscussionPerson = { id: string; full_name: string; role: string };
export type DiscussionAttachment = { id: string; name: string | null; content_type: string; shareable: boolean; created_at: string };
export type Discussion = {
  id: string; topic: string; discussion_date: string; department: string | null; decision: string | null; responsible: DiscussionPerson | null;
  deadline: string | null; status: DiscussionStatus; follow_up_date: string | null; created_at: string; updated_at: string;
};
export type DiscussionDetail = Discussion & {
  points: string | null; participants: DiscussionPerson[]; attachments: DiscussionAttachment[]; created_by: DiscussionPerson | null; updated_by: DiscussionPerson | null;
};
export type DiscussionPage = { items: Discussion[]; total: number; limit: number; offset: number };
export type DiscussionOptions = { users: DiscussionPerson[] };
export type DiscussionFilters = { status: string; offset: number };
export type MyDecision = { id: string; decision: string; deadline: string | null; status: DiscussionStatus; attachments: { id: string; name: string | null; content_type: string }[]; updated_at: string };

export const STATUS_LABEL: Record<DiscussionStatus, string> = { open: "Open", in_progress: "In Progress", completed: "Completed", cancelled: "Cancelled" };
/** What the responsible person may set (MD8); cancelling is management's. */
export const MY_STATUSES: DiscussionStatus[] = ["open", "in_progress", "completed"];

const ROLE_WORDS: Record<string, string> = { bdm: "BDM", it: "IT", hr: "HR", admin: "Administrator" };

/** "partnership_manager" -> "Partnership Manager", "bdm_manager" -> "BDM Manager": a staff member's role as the pickers show it. */
export function roleLabel(role: string): string {
  return role.split("_").map((word) => ROLE_WORDS[word] ?? word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}

export function statusClass(status: DiscussionStatus): string {
  return { open: "badge", in_progress: "status pending", completed: "status", cancelled: "status error" }[status];
}

const STATUS_SHAPE = /^(open|in_progress|completed|cancelled)$/;

/** The filters from the page's search params; a malformed or repeated value only comes from a hand-edited address and is dropped. */
export function discussionFilters(search: Record<string, string | string[] | undefined>): DiscussionFilters {
  const one = (key: string) => (typeof search[key] === "string" ? (search[key] as string) : "");
  const offset = Number.parseInt(one("offset"), 10);
  return { status: STATUS_SHAPE.test(one("status")) ? one("status") : "", offset: offset > 0 && offset <= 10_000 ? offset : 0 };
}

function query(filters: DiscussionFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.offset > 0) params.set("offset", String(filters.offset));
  return params;
}

export function discussionsHref(filters: DiscussionFilters): string {
  const text = query(filters).toString();
  return text ? `${DISCUSSIONS_HOME}?${text}` : DISCUSSIONS_HOME;
}

export function discussionsUrl(filters: DiscussionFilters): string {
  const params = query(filters);
  params.set("limit", String(DISCUSSIONS_PAGE_SIZE));
  return `${DISCUSSIONS_API}?${params}`;
}

const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

/** "2026-10-10" -> "10 Oct 2026" (a calendar date, no time zone shift). */
export function formatDay(day: string): string {
  return DAY.format(new Date(`${day}T00:00:00Z`));
}

/** The §27 example's shape: "Proceed with agreement — 10 Oct 2026 — In Progress". */
export function decisionLine(item: { decision: string; deadline: string | null; status: DiscussionStatus }): string {
  return `${item.decision} — ${item.deadline ? formatDay(item.deadline) : "no deadline"} — ${STATUS_LABEL[item.status]}`;
}

/** An open or in-progress decision whose deadline (an India calendar date) has passed. */
export function isOverdue(item: { deadline: string | null; status: DiscussionStatus }, today: string): boolean {
  return item.deadline !== null && (item.status === "open" || item.status === "in_progress") && item.deadline < today;
}

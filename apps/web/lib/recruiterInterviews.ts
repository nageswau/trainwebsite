// rec-020 (DEC-SCOPE-139): interviews -- types, the EVID-018 §14 round labels, the views, the endpoints and the notice wording. The API
// decides scope, every rule (the moves, AC2's after-the-time gate, the clash) and what the viewer may do (`allowed_statuses`, `can_edit`,
// `can_reschedule`, `can_schedule`); the UI only offers what it allows.
import { isPage, type Page } from "@/lib/apiErrors";

/** EVID-018 §14 (L626-L634), in source order and wording. */
export const ROUNDS = [
  { key: "hr_round", label: "HR Round" },
  { key: "technical_round", label: "Technical Round" },
  { key: "manager_round", label: "Manager Round" },
  { key: "final_round", label: "Final Round" },
  { key: "client_round", label: "Client Round" },
] as const;
export type Round = (typeof ROUNDS)[number]["key"];
/** §14 L638-L652: the history names statuses by key. */
export const STATUS_LABELS: Record<string, string> = {
  scheduled: "Scheduled", confirmed: "Confirmed", completed: "Completed", rescheduled: "Rescheduled", no_show: "No Show",
  selected: "Selected", rejected: "Rejected", on_hold: "On Hold",
};

type PersonRef = { id: string; full_name: string };
type StatusOption = { key: string; label: string };
export type InterviewEvent = {
  event: "scheduled" | "rescheduled" | "status"; from_status: string | null; to_status: string | null; old_scheduled_at: string | null;
  new_scheduled_at: string | null; note: string | null; actor: PersonRef | null; created_at: string;
};
export type RecInterview = {
  id: string; code: string; round: Round | null; round_label: string | null; scheduled_at: string; mode: string; meeting_url: string | null;
  interviewer: string | null; location: string | null; status: string; status_label: string; result: string | null;
  application: { id: string; status: string; status_label: string }; candidate: { id: string; code: string; name: string };
  requirement: { id: string; code: string; title: string }; company: { id: string; name: string }; contact: { id: string; name: string } | null;
  history: InterviewEvent[]; allowed_statuses: StatusOption[]; can_edit: boolean; can_reschedule: boolean;
};
export type Notices = { candidate: string; contact: string | null };
export type ApplicationInterviews = { items: RecInterview[]; can_schedule: boolean };
export type InterviewView = "upcoming" | "awaiting_update" | "on_hold" | "closed";
export const VIEW_TABS: [InterviewView, string][] = [["upcoming", "Upcoming"], ["awaiting_update", "Awaiting update"], ["on_hold", "On hold"], ["closed", "Closed"]];
export type InterviewListPage = Page<RecInterview> & { counts: Record<InterviewView, number> };

export const INTERVIEWS_URL = "/api/v1/recruiter/interviews";
export const INTERVIEWS_PATH = "/recruiter/interviews";
export const LIST_LIMIT = 50;
export const NOTE_MAX = 500;
export const interviewUrl = (id: string, action?: "reschedule" | "status") => `${INTERVIEWS_URL}/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;
export const applicationInterviewsUrl = (applicationId: string) => `/api/v1/recruiter/applications/${encodeURIComponent(applicationId)}/interviews`;

export function interviewsUrl(view: InterviewView, offset = 0): string {
  return `${INTERVIEWS_URL}?${new URLSearchParams({ view, limit: String(LIST_LIMIT), offset: String(offset) })}`;
}

export const isView = (value: string | null): value is InterviewView => VIEW_TABS.some(([key]) => key === value);

export function isRecInterview(data: unknown): data is RecInterview {
  const d = data as Partial<RecInterview> | null;
  return !!d && typeof d.id === "string" && typeof d.scheduled_at === "string" && Array.isArray(d.history) && Array.isArray(d.allowed_statuses);
}

/** The schedule / reschedule / status replies carry `{interview, notifications?}`; PATCH replies with the item itself. */
export function interviewOf(data: unknown): RecInterview | null {
  if (isRecInterview(data)) return data;
  const inner = (data as { interview?: unknown } | null)?.interview;
  return isRecInterview(inner) ? inner : null;
}

export function isApplicationInterviews(data: unknown): data is ApplicationInterviews {
  const d = data as Partial<ApplicationInterviews> | null;
  return !!d && Array.isArray(d.items) && typeof d.can_schedule === "boolean" && d.items.every(isRecInterview);
}

export function isInterviewListPage(data: unknown): data is InterviewListPage {
  return isPage(data) && !!(data as { counts?: unknown }).counts;
}

const NOTICE: Record<string, string> = {
  queued: "email queued", in_app: "notified in the portal", no_email: "no email address", email_off: "email is not set up", off: "not notified",
};

/** IV9: what happened to each notice, in words ("Candidate: email queued. Contact: no email address."). */
export function noticeText(notices: Notices | undefined): string {
  if (!notices) return "";
  const parts = [`Candidate: ${NOTICE[notices.candidate] ?? notices.candidate}.`];
  if (notices.contact) parts.push(`Contact: ${NOTICE[notices.contact] ?? notices.contact}.`);
  return parts.join(" ");
}

/** The candidate's day of an interview in IST (the calendar grouping of Upcoming). */
export function istDay(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short", year: "numeric" }).format(new Date(iso));
}

// rec-020 (DEC-SCOPE-148): interviews -- types, the EVID-018 §14 round labels, the views, the endpoints and the notice wording. The API
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
  selected: "Selected", rejected: "Rejected", on_hold: "On Hold", cancelled: "Cancelled",
};

// hrc-028 (DEC-SCOPE-399 I1/I2): the meeting platforms (the API's order), the candidate's zone and the length of the interview.
export const PLATFORMS = [
  { key: "google_meet", label: "Google Meet" },
  { key: "microsoft_teams", label: "Microsoft Teams" },
  { key: "zoom", label: "Zoom" },
  { key: "zoho_meeting", label: "Zoho Meeting" },
  { key: "other", label: "Other" },
] as const;
export const IST_ZONE = "Asia/Kolkata";
/** Common candidate zones; the API accepts any IANA name, and a stored one outside this list is kept as an option. */
export const TIME_ZONES = [
  IST_ZONE, "Asia/Dubai", "Asia/Riyadh", "Asia/Qatar", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney", "Europe/London", "Europe/Berlin",
  "America/New_York", "America/Chicago", "America/Los_Angeles",
];
export const zoneOptions = (stored?: string | null): string[] => (stored && !TIME_ZONES.includes(stored) ? [...TIME_ZONES, stored] : TIME_ZONES);
export const DURATIONS = ["15", "30", "45", "60", "90", "120", "180", "240"];
export const PHONE_MAX = 200;
export const INSTRUCTIONS_MAX = 2000;
export const DOCUMENTS_MAX = 1000;

/** The interview's length in minutes as the form's select value ("" = no end set). */
export function durationOf(i: Pick<RecInterview, "scheduled_at" | "ends_at">): string {
  return i.ends_at ? String(Math.round((Date.parse(i.ends_at) - Date.parse(i.scheduled_at)) / 60000)) : "";
}

/** The end the API stores: the start plus the chosen minutes (null = none). */
export function endsAt(startIso: string, minutes: string): string | null {
  return minutes && startIso ? new Date(Date.parse(startIso) + Number(minutes) * 60000).toISOString() : null;
}

type PersonRef = { id: string; full_name: string };
type StatusOption = { key: string; label: string };
export type InterviewEvent = {
  event: "scheduled" | "rescheduled" | "status" | "details"; from_status: string | null; to_status: string | null; old_scheduled_at: string | null;
  new_scheduled_at: string | null; note: string | null; actor: PersonRef | null; created_at: string;
  // hrc-028 (I4): a `details` event's replaced link / location -- staff only
  old_meeting_url?: string | null; new_meeting_url?: string | null; old_location?: string | null; new_location?: string | null;
};
/** rec-021 (FB3): the decisions are the interview's own decision statuses. */
export const DECISIONS = ["selected", "rejected", "on_hold"] as const;
export type Decision = (typeof DECISIONS)[number];
export type FeedbackFields = {
  technical_rating: number | null; communication_rating: number | null; overall_rating: number; strengths: string | null; weaknesses: string | null;
  recruiter_comments: string | null; company_feedback: string | null; next_round: Round | null; final_decision: Decision | null;
};
export type InterviewFeedback = FeedbackFields & {
  next_round_label: string | null; final_decision_label: string | null; recorded_by: PersonRef; updated_at: string;
};
export const FEEDBACK_TEXT_MAX = 2000;

export type RecInterview = {
  id: string; code: string; round: Round | null; round_label: string | null; scheduled_at: string; mode: string; meeting_url: string | null;
  interviewer: string | null; location: string | null; status: string; status_label: string; result: string | null;
  application: { id: string; status: string; status_label: string }; candidate: { id: string; code: string; name: string };
  requirement: { id: string; code: string; title: string }; company: { id: string; name: string }; contact: { id: string; name: string } | null;
  history: InterviewEvent[]; allowed_statuses: StatusOption[]; can_edit: boolean; can_reschedule: boolean;
  feedback: InterviewFeedback | null; can_feedback: boolean; updated_at: string; // hrc-003: the edit form's token
  // hrc-028 (I1/I3): `local_when` is the start and end in the candidate's zone, as the notices and the portal show it
  round_number: number | null; ends_at: string | null; time_zone: string; local_when: string; platform: string | null; platform_label: string | null;
  phone_details: string | null; instructions: string | null; documents_required: string | null; cancel_reason: string | null; can_cancel: boolean;
};
export type Notices = { candidate: string; contact: string | null };
export type ApplicationInterviews = { items: RecInterview[]; can_schedule: boolean };
export type InterviewView = "upcoming" | "awaiting_update" | "on_hold" | "closed";
export const VIEW_TABS: [InterviewView, string][] = [["upcoming", "Upcoming"], ["awaiting_update", "Awaiting update"], ["on_hold", "On hold"], ["closed", "Closed"]];
export type InterviewListPage = Page<RecInterview> & { counts: Record<InterviewView, number> };

export const INTERVIEWS_URL = "/api/v1/recruiter/interviews";
export const LIST_LIMIT = 50;
export const NOTE_MAX = 500;
export const interviewUrl = (id: string, action?: "reschedule" | "status" | "feedback" | "cancel") => `${INTERVIEWS_URL}/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;
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

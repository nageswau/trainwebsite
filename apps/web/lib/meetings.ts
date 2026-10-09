// upc-009 (DEC-SCOPE-145): university meetings (§7) -- types, words, URLs and list helpers shared by the meeting pages and forms. The
// university, responsible-employee and employee pickers are upc-010's (`lib/visits`), which apply the same roles and scope.
import type { Overlap } from "@/lib/partnershipCalendar";
import type { ManagerRef } from "@/lib/telecaller";
import type { VisitUniversity } from "@/lib/visits";

// MG1: the §7 meeting types, in source order and wording (= app/partnership_meeting_types.py TYPES).
export const MEETING_TYPES: Record<string, string> = {
  introduction: "Introduction", partnership_discussion: "Partnership discussion", commercial_discussion: "Commercial discussion",
  mou_discussion: "MoU discussion", product_presentation: "Product presentation", student_recruitment_discussion: "Student recruitment discussion",
  application_process_discussion: "Application process discussion", marketing_discussion: "Marketing discussion", university_visit: "University visit",
  campus_visit: "Campus visit", webinar: "Webinar", training_session: "Training session",
};
export const MODES: Record<string, string> = { online: "Online", offline: "Offline" }; // MG4 (§7 "Online/Offline")
export const MEETING_STATUSES: Record<string, string> = { scheduled: "Scheduled", completed: "Completed", cancelled: "Cancelled" };
export const EVENT_LABELS: Record<string, string> = {
  scheduled: "Scheduled", edited: "Edited", rescheduled: "Rescheduled", completed: "Outcome recorded", cancelled: "Cancelled",
};
// MG16: the four lists, in tab order, with what an empty one says.
export const VIEWS = ["upcoming", "awaiting_outcome", "completed", "cancelled"] as const;
export type MeetingView = (typeof VIEWS)[number];
export const VIEW_LABELS: Record<MeetingView, string> = { upcoming: "Upcoming", awaiting_outcome: "Awaiting outcome", completed: "Completed", cancelled: "Cancelled" };
export const VIEW_EMPTY: Record<MeetingView, string> = {
  upcoming: "No upcoming meetings.", awaiting_outcome: "No meetings are waiting for an outcome.", completed: "No completed meetings yet.",
  cancelled: "No cancelled meetings.",
};
export const LINK_MISSING_TEXT = "This online meeting has no link yet. Add it before the meeting."; // MG4 / E1
export const LIMITS = { location: 200, meeting_url: 500, agenda: 2000, notes: 2000, discussion_points: 4000, decisions: 2000, next_action: 200, reason: 1000 } as const;

export type MeetingContact = { id: string | null; name: string | null; designation: string | null };
export type MeetingRow = {
  id: string; code: string; university: VisitUniversity; meeting_type: string; starts_at: string; mode: string; status: string;
  responsible: ManagerRef; contact: MeetingContact | null; warnings: string[];
};
export type MeetingEvent = { event: string; old_starts_at: string | null; new_starts_at: string | null; reason: string | null; actor: ManagerRef; created_at: string };
export type MeetingFollowUp = { id: string; title: string; due_on: string; status: string; assignee: ManagerRef };
export type MeetingPermissions = { can_edit: boolean; can_complete: boolean; can_cancel: boolean };
export type Meeting = MeetingRow & {
  location: string | null; meeting_url: string | null; agenda: string | null; notes: string | null; discussion_points: string | null;
  decisions: string | null; next_action: string | null; next_action_due_on: string | null; next_meeting_date: string | null;
  created_by: ManagerRef; completed_by: ManagerRef | null; completed_at: string | null; cancelled_at: string | null; cancel_reason: string | null;
  participants: { contacts: { id: string; name: string; designation: string | null }[]; employees: ManagerRef[] };
  events: MeetingEvent[]; follow_ups: MeetingFollowUp[]; permissions: MeetingPermissions; created_at: string; updated_at: string;
  overlaps?: Overlap[]; // upc-011 CL11
};
export type MeetingPage = { items: MeetingRow[]; total: number; limit: number; offset: number; counts: Record<MeetingView, number> };

export const MEETINGS_URL = "/api/v1/partnership/meetings";
export const MEETINGS_PATH = "/partnership/meetings";
export const meetingUrl = (id: string, action?: string) => `${MEETINGS_URL}/${id}${action ? `/${action}` : ""}`;
export const meetingPath = (id: string, edit = false) => `${MEETINGS_PATH}/${id}${edit ? "/edit" : ""}`;
export const newMeetingPath = (universityId?: string) => `${MEETINGS_PATH}/new${universityId ? `?university=${encodeURIComponent(universityId)}` : ""}`;

// MG14/MG15: who reads and who schedules (the API decides; this only hides links and skips a read that would be refused).
export const SCHEDULER_ROLES = new Set(["partnership_manager", "partnership_head"]);
export const MEETING_READERS = new Set([...SCHEDULER_ROLES, "super_admin"]);

/** An instant shown in IST, e.g. "18 Oct 2026, 10:00". */
export const meetingWhen = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" });

export const contactText = (c: MeetingContact | null) => (c?.name ? `${c.name}${c.designation ? ` (${c.designation})` : ""}` : "—");

// The list's filters travel in the page URL; only these keys are passed on to the API.
export const MEETING_FILTER_KEYS = ["view", "university_id", "mine"] as const;
export type MeetingFilters = Partial<Record<(typeof MEETING_FILTER_KEYS)[number] | "offset", string>>;

export const viewOf = (value: string | undefined): MeetingView => (VIEWS as readonly string[]).includes(value ?? "") ? (value as MeetingView) : "upcoming";

function filterParams(filters: MeetingFilters): URLSearchParams {
  const query = new URLSearchParams();
  for (const key of MEETING_FILTER_KEYS) {
    const value = filters[key]?.trim();
    if (value) query.set(key, value);
  }
  return query;
}

export function meetingListQuery(filters: MeetingFilters, limit: number, offset: number): string {
  const query = filterParams({ ...filters, view: viewOf(filters.view) });
  query.set("limit", String(limit));
  query.set("offset", String(offset));
  return query.toString();
}

export function meetingPageHref(filters: MeetingFilters, offset = 0): string {
  const query = filterParams(filters);
  if (offset > 0) query.set("offset", String(offset));
  const text = query.toString();
  return text ? `${MEETINGS_PATH}?${text}` : MEETINGS_PATH;
}

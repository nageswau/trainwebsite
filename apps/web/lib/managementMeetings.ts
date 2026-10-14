import { isoToIstInput } from "@/lib/bdmAppointments";
import { type DiscussionPerson, type DiscussionStatus } from "@/lib/managementDiscussions";
import { type CalendarView } from "@/lib/partnershipCalendar";
import { type TaskPriority } from "@/lib/managementTasks";

// mgmt-029 (spec MM1-MM14): management meetings and the minutes chain -- types, labels, calendar links and the roll-up's words. The API
// decides access (the operational tier; each participant's own meetings) and every rule; this module only shapes what the pages send
// and show. Week / month ranges reuse the partnership calendar's helpers (upc-011 CL13), all on IST calendar dates.
export const MEETINGS_HOME = "/management/meetings";
export const MEETINGS_API = "/api/v1/management/meetings";
export const MY_MEETINGS_API = "/api/v1/me/management-meetings";

export type MeetingKind = "partner" | "department" | "school" | "university" | "agent" | "recruiter" | "marketing_review";
export type MeetingStatus = "scheduled" | "completed" | "cancelled";
export type MeetingMode = "Online" | "Phone" | "In person";

/** EVID-017 §29's seven kinds, in source order and wording (MM1). */
export const KIND_LABEL: Record<MeetingKind, string> = {
  partner: "Partner meeting", department: "Department meeting", school: "School meeting", university: "University meeting",
  agent: "Agent meeting", recruiter: "Recruiter meeting", marketing_review: "Marketing review",
};
export const STATUS_LABEL: Record<MeetingStatus, string> = { scheduled: "Scheduled", completed: "Completed", cancelled: "Cancelled" };
export const MODES: MeetingMode[] = ["Online", "Phone", "In person"];

export type Meeting = {
  id: string; title: string; kind: MeetingKind; starts_at: string; mode: MeetingMode; location: string | null; meeting_url: string | null;
  status: MeetingStatus; participant_count: number;
};
export type ChainTask = { id: string; title: string; owner: DiscussionPerson; priority: TaskPriority; deadline: string; status: DiscussionStatus };
export type ChainDecision = { id: string; decision: string; responsible: DiscussionPerson | null; deadline: string | null; status: DiscussionStatus; tasks: ChainTask[] };
export type MeetingDetail = Meeting & {
  agenda: string | null; minutes: string | null; minutes_recorded_at: string | null; participants: DiscussionPerson[];
  decisions: ChainDecision[]; tasks: ChainTask[]; progress: { done: number; total: number };
  created_by: DiscussionPerson | null; updated_by: DiscussionPerson | null; created_at: string; updated_at: string;
};
export type MeetingPage = { items: Meeting[]; date_from: string; date_to: string; today: string };
export type MyMeeting = Pick<Meeting, "id" | "title" | "kind" | "starts_at" | "mode" | "location" | "meeting_url" | "status"> & { agenda: string | null };

export function statusClass(status: MeetingStatus): string {
  return { scheduled: "badge", completed: "status", cancelled: "status error" }[status];
}

/** The IST calendar day of a start time ("2026-10-14"). */
export const istDay = (iso: string): string => isoToIstInput(iso).slice(0, 10);
/** "09:30" -- the IST clock time of a start. */
export const istTime = (iso: string): string => isoToIstInput(iso).slice(11, 16);

/** The meetings on one IST day, in the API's (start time) order. */
export const meetingsOn = <T extends { starts_at: string }>(items: T[], day: string): T[] => items.filter((m) => istDay(m.starts_at) === day);

export function calendarHref(view: CalendarView, date: string): string {
  return `${MEETINGS_HOME}?${new URLSearchParams({ view, date })}`;
}

export function calendarUrl(from: string, to: string): string {
  return `${MEETINGS_API}?${new URLSearchParams({ date_from: from, date_to: to })}`;
}

/** MM10's roll-up in words: "2 of 5 completed", or what is still missing. */
export function progressText(progress: { done: number; total: number }): string {
  return progress.total === 0 ? "No decisions or tasks yet" : `${progress.done} of ${progress.total} completed`;
}

/** Only an http(s) link is ever rendered as a link (MM3; the API refuses any other scheme too). */
export const safeLink = (url: string | null): string | null => (url && /^https?:\/\//i.test(url) ? url : null);

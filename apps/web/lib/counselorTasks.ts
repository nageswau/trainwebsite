// ccrm-029 (DEC-SCOPE-250, T1-T8): counselor tasks -- types, bands, filters and links. The API decides access (a counselor's own tasks;
// the Overseas Admin's are everyone's), every rule, each task's band (IST days) and `can_edit`; the UI only offers what it allows.
import type { TaskPriority } from "@/lib/managementTasks";
import { formatDay } from "@/lib/managementDiscussions";

export const COUNSELOR_TASKS_API = "/api/v1/counselor/tasks";
export const COUNSELOR_TASKS_HOME = "/overseas/counselor/tasks";
export const ADMIN_TASKS_HOME = "/overseas/admin/counselor-tasks";
export const COUNSELOR_FOLLOW_UPS_API = "/api/v1/counselor/follow-ups";
export const LIST_LIMIT = 200;

export type CounselorTaskStatus = "open" | "done" | "cancelled";
export type CounselorTaskBand = "overdue" | "today" | "upcoming" | "done" | "cancelled";
export type LinkType = "lead" | "student" | "application";
export type CounselorTaskLink = { type: LinkType; id: string; label: string };
export type CounselorTask = {
  id: string; title: string; due_on: string; priority: TaskPriority; status: CounselorTaskStatus; band: CounselorTaskBand | null; source: string;
  completed_at: string | null; link: CounselorTaskLink | null; counselor: { id: string; full_name: string }; created_by: { id: string; full_name: string };
  created_at: string; updated_at: string; can_edit: boolean;
};
export type CounselorTaskCounts = Record<"overdue" | "today" | "upcoming" | "done", number>;
export type CounselorTaskPage = { items: CounselorTask[]; total: number; limit: number; offset: number; today: string; counts: CounselorTaskCounts };
export type LinkOption = { id: string; label: string };
export type CounselorTaskOptions = {
  counselors: { id: string; full_name: string }[];
  links: { leads: LinkOption[]; students: LinkOption[]; applications: LinkOption[] };
};

/** T6: the bands in order; the marker is decoration, the name carries the meaning. */
export const BANDS: { band: CounselorTaskBand; label: string; marker: string }[] = [
  { band: "overdue", label: "Overdue", marker: "🔴" },
  { band: "today", label: "Today", marker: "🟠" },
  { band: "upcoming", label: "Upcoming", marker: "⚪" },
  { band: "done", label: "Done (last 7 days)", marker: "🟢" },
  { band: "cancelled", label: "Cancelled", marker: "⚫" },
];
export const LINK_GROUPS: { type: LinkType; key: keyof CounselorTaskOptions["links"]; label: string }[] = [
  { type: "lead", key: "leads", label: "Leads" },
  { type: "student", key: "students", label: "Students" },
  { type: "application", key: "applications", label: "Applications" },
];
export const LINK_TYPE_LABEL: Record<LinkType, string> = { lead: "Lead", student: "Student", application: "Application" };

export function groupByBand(items: CounselorTask[]) {
  return BANDS.map((b) => ({ ...b, items: items.filter((item) => item.band === b.band) })).filter((group) => group.items.length > 0);
}

/** "Call the bank — due 12 Oct 2026"; the list shows the priority as a badge beside it (QA-01). */
export function taskLine(task: { title: string; due_on: string }): string {
  return `${task.title} — due ${formatDay(task.due_on)}`;
}

/** The counselor's page for a linked record; the admin's list shows the label only. */
export function linkHref(link: { type: LinkType; id: string }): string {
  const id = encodeURIComponent(link.id);
  return { lead: `/overseas/counselor/leads/${id}`, student: `/overseas/counselor/students/${id}/notes`, application: "/overseas/counselor/applications" }[link.type];
}

/** The form's `<select>` value for a link ("lead:<id>"), and back. */
export const linkValue = (link: { type: LinkType; id: string } | null) => (link ? `${link.type}:${link.id}` : "");
export function parseLink(value: string): { type: LinkType; id: string } | null {
  const [type, id] = value.split(":");
  return id && (type === "lead" || type === "student" || type === "application") ? { type, id } : null;
}

// --- the admin's filters (search params) -------------------------------------------------------------------------------------------
export type AdminFilters = { counselor: string; band: CounselorTaskBand | "" };
const FILTER_BANDS = new Set<string>(BANDS.map((b) => b.band));

export function adminFilters(search: Record<string, string | string[] | undefined>): AdminFilters {
  const one = (value: string | string[] | undefined) => (typeof value === "string" ? value : "");
  const band = one(search.band);
  const counselor = one(search.counselor);
  return { counselor: /^[0-9a-f-]{36}$/i.test(counselor) ? counselor : "", band: FILTER_BANDS.has(band) ? (band as CounselorTaskBand) : "" };
}

export function adminTasksUrl(filters: AdminFilters): string {
  const params = new URLSearchParams({ limit: String(LIST_LIMIT) });
  if (filters.counselor) params.set("counselor_id", filters.counselor);
  if (filters.band) params.set("band", filters.band);
  return `${COUNSELOR_TASKS_API}?${params}`;
}

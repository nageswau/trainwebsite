import { isPage, type Page } from "@/lib/apiErrors";
import type { ManagerRef } from "@/lib/telecaller";

// upc-020 (DEC-SCOPE-139): partnership follow-ups and tasks (§19/§20) -- types, words and URLs. The API decides every rule (TK8-TK13);
// `permissions` only tells the UI which actions to offer.
export const TASKS_URL = "/api/v1/partnership/tasks";
export const TASKS_PATH = "/partnership/tasks";
export const TASK_PAGE = 50;
export const TITLE_MAX = 200;
export const NOTES_MAX = 2000;

// §20's four bands in source order (L690-L693), then the closed items.
export const BANDS = ["overdue", "today", "tomorrow", "upcoming", "done", "cancelled"] as const;
export type Band = (typeof BANDS)[number];
export const BAND_LABEL: Record<Band, string> = {
  overdue: "Overdue", today: "Due today", tomorrow: "Due tomorrow", upcoming: "Upcoming", done: "Done", cancelled: "Cancelled",
};
export const EMPTY_TEXT: Record<Band, string> = {
  overdue: "Nothing overdue.", today: "Nothing due today.", tomorrow: "Nothing due tomorrow.", upcoming: "Nothing upcoming.", done: "Nothing done yet.",
  cancelled: "Nothing cancelled.",
};
export const KINDS = ["follow_up", "task"] as const;
export type TaskKind = (typeof KINDS)[number];
export const KIND_LABEL: Record<TaskKind, string> = { follow_up: "Follow-up", task: "Task" };
export const PRIORITIES = ["high", "medium", "low"] as const;
export const PRIORITY_LABEL: Record<string, string> = { high: "High", medium: "Medium", low: "Low" };
export const SOURCE_LABEL: Record<string, string> = {
  manual: "Added by hand", stage: "Auto: stage change", visit: "Auto: university visit", meeting: "Auto: meeting", agreement: "Auto: agreement",
};

// TK8/TK9: who reads and who adds (the API decides; this only hides links and skips a read that would be refused).
export const TASK_READERS = new Set(["partnership_manager", "partnership_head", "super_admin"]);
export const TASK_CREATORS = new Set(["partnership_manager", "partnership_head"]);

export type TaskPermissions = { can_edit: boolean; can_reschedule: boolean; can_complete: boolean; can_cancel: boolean };
export type PartnershipTask = {
  id: string; university: { id: string; university_code: string; name: string }; kind: TaskKind; title: string; notes: string | null;
  due_on: string; priority: string; status: "open" | "done" | "cancelled"; band: string; overdue: boolean; source: string;
  assignee: ManagerRef; created_by: ManagerRef; completed_at: string | null; cancelled_at: string | null; cancel_reason: string | null;
  created_at: string; updated_at: string; permissions: TaskPermissions;
};
export type TaskPage = Page<PartnershipTask> & { today: string; counts: Record<Band, number> };
export type UniversityFollowUpData = {
  next_action: { id: string; title: string; due_on: string; priority: string; band: string; assignee: ManagerRef } | null;
  last_action: { title: string; at: string } | null;
};
export type TaskQuery = { band: Band | "open"; assignee?: string; university?: string; offset?: number };

export const taskUrl = (id: string, action?: string) => `${TASKS_URL}/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;

export function tasksUrl(q: TaskQuery): string {
  const query = new URLSearchParams({ band: q.band, limit: String(TASK_PAGE), offset: String(q.offset ?? 0) });
  if (q.assignee) query.set("assignee", q.assignee);
  if (q.university) query.set("university_id", q.university);
  return `${TASKS_URL}?${query}`;
}

export function isTask(data: unknown): data is PartnershipTask {
  const d = data as Partial<PartnershipTask> | null;
  return !!d && typeof d.id === "string" && typeof d.title === "string" && typeof d.due_on === "string" && !!d.permissions;
}

/** The API's `{task}` envelope, or null when the body is not one. */
export const taskOf = (data: unknown): PartnershipTask | null => {
  const task = (data as { task?: unknown } | null)?.task;
  return isTask(task) ? task : null;
};

export function isTaskPage(data: unknown): data is TaskPage {
  const counts = (data as { counts?: unknown } | null)?.counts;
  return isPage(data) && typeof counts === "object" && counts !== null;
}

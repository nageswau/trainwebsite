import { formatDay, type DiscussionPerson, type DiscussionStatus } from "@/lib/managementDiscussions";

// mgmt-028 (spec MT1-MT14): the management to-do and each staff member's "Management tasks" -- types, bands, views and links. The API
// decides access (the operational tier for the to-do; the owner for their own tasks), every rule and each task's band (IST, MT3).
export const TASKS_HOME = "/management/tasks";
export const TASKS_API = "/api/v1/management/tasks";
export const MY_TASKS_HOME = "/account/management-tasks";
export const MY_TASKS_API = "/api/v1/me/management-tasks";
const LIMIT = 200;

export type TaskStatus = DiscussionStatus; // the same four statuses (MT2)
export type TaskPriority = "high" | "medium" | "low";
export type TaskBand = "overdue" | "today" | "week" | "later" | "completed" | "cancelled";
export type ManagementTask = {
  id: string; title: string; owner: DiscussionPerson; owner_active: boolean; priority: TaskPriority; deadline: string; status: TaskStatus;
  band: TaskBand | null; source: string; completed_at: string | null; created_by: DiscussionPerson; created_at: string; updated_at: string;
};
export type MyTask = { id: string; title: string; priority: TaskPriority; deadline: string; status: TaskStatus; band: TaskBand | null; updated_at: string };
export type TaskCounts = Record<"overdue" | "today" | "week" | "later" | "completed", number>;
export type TaskPage = { items: ManagementTask[]; total: number; limit: number; offset: number; today: string; counts: TaskCounts };
export type MyTaskPage = { items: MyTask[]; today: string; counts: TaskCounts };
export type TaskView = "mine" | "everyone" | "cancelled";
export type TaskFilters = { view: TaskView };

/** EVID-017 §28's bands in source order; Later (MT3) keeps tasks beyond this week in view. */
export const BANDS: { band: TaskBand; label: string; marker: string }[] = [
  { band: "overdue", label: "Overdue", marker: "🔴" },
  { band: "today", label: "Due Today", marker: "🟠" },
  { band: "week", label: "This Week", marker: "🟡" },
  { band: "later", label: "Later", marker: "⚪" },
  { band: "completed", label: "Completed", marker: "🟢" },
  { band: "cancelled", label: "Cancelled", marker: "⚫" },
];
export const PRIORITY_LABEL: Record<TaskPriority, string> = { high: "High", medium: "Medium", low: "Low" };
export const VIEWS: { view: TaskView; label: string }[] = [{ view: "mine", label: "My tasks" }, { view: "everyone", label: "Everyone" }, { view: "cancelled", label: "Cancelled" }];

export function priorityClass(priority: TaskPriority): string {
  return { high: "status error", medium: "status pending", low: "badge" }[priority];
}

/** The non-empty bands, in order, each with its items in the API's order. */
export function groupByBand<T extends { band: TaskBand | null }>(items: T[]): { band: TaskBand; label: string; marker: string; items: T[] }[] {
  return BANDS.map((b) => ({ ...b, items: items.filter((item) => item.band === b.band) })).filter((group) => group.items.length > 0);
}

/** The view from the page's search params; anything else (or a repeated param) is "My tasks", §28's own list. */
export function taskFilters(search: Record<string, string | string[] | undefined>): TaskFilters {
  const view = search.view;
  return { view: view === "everyone" || view === "cancelled" ? view : "mine" };
}

export function tasksHref(filters: TaskFilters): string {
  return filters.view === "mine" ? TASKS_HOME : `${TASKS_HOME}?view=${filters.view}`;
}

export function tasksUrl(filters: TaskFilters): string {
  const params = new URLSearchParams();
  if (filters.view === "mine") params.set("owner", "me");
  if (filters.view === "cancelled") params.set("band", "cancelled");
  params.set("limit", String(LIMIT));
  return `${TASKS_API}?${params}`;
}

/** "Approve marketing budget — 10 Oct 2026 — High priority" (the notification's wording too). */
export function taskLine(task: { title: string; deadline: string; priority: TaskPriority }): string {
  return `${task.title} — ${formatDay(task.deadline)} — ${PRIORITY_LABEL[task.priority]} priority`;
}

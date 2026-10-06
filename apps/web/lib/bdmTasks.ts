import { isPage, type Page } from "@/lib/apiErrors";
import { ORG_TYPE_LABEL, type OrgType } from "@/lib/bdmOrganizations";

// bdm-008 (DEC-SCOPE-074, spec §6, §9): follow-up and task types, labels and URLs. The API decides every rule; `permissions` only tells
// the UI which actions to offer.
export const TASKS_URL = "/api/v1/bdm/tasks";
export const TABS = ["today", "overdue", "upcoming", "done", "cancelled"] as const;
export type Tab = (typeof TABS)[number];
export const TAB_LABEL: Record<Tab, string> = { today: "Today", overdue: "Overdue", upcoming: "Upcoming", done: "Done", cancelled: "Cancelled" };
export const EMPTY_TEXT: Record<Tab, string> = {
  today: "Nothing due today.", overdue: "No overdue follow-ups.", upcoming: "Nothing upcoming.", done: "Nothing done yet.", cancelled: "Nothing cancelled.",
};
export const KINDS = ["follow_up", "task"] as const;
export type TaskKind = (typeof KINDS)[number];
export const KIND_LABEL: Record<TaskKind, string> = { follow_up: "Follow-up", task: "Task" };
export const TITLE_MAX = 200;
export const NOTES_MAX = 2000;
export const TASK_PAGE = 50;

export type Task = {
  id: string; kind: TaskKind; title: string; notes: string | null; due_on: string; status: "open" | "done" | "cancelled";
  source: "appointment_outcome" | "mou" | "manual"; overdue: boolean;
  organization: { id: string; code: string; name: string; org_type: OrgType; archived: boolean } | null;
  appointment: { id: string; code: string } | null; assignee: { id: string; full_name: string; active: boolean };
  completed_at: string | null; cancelled_at: string | null; cancel_reason: string | null; created_at: string; updated_at: string;
  permissions: { can_edit: boolean; can_complete: boolean; can_cancel: boolean };
};
export type TypeCount = { org_type: OrgType | null; count: number };
export type TaskPage = Page<Task> & { today: string; counts: { buckets: Record<Tab, number>; by_org_type: TypeCount[] } };
export type TaskQuery = { bucket: Tab | "open"; kind?: string; orgType?: string; organization?: string; bdm?: string; offset?: number };

export const taskUrl = (id: string) => `${TASKS_URL}/${encodeURIComponent(id)}`;

export function tasksUrl(q: TaskQuery): string {
  const query = new URLSearchParams({ bucket: q.bucket, limit: String(TASK_PAGE), offset: String(q.offset ?? 0) });
  if (q.kind) query.set("kind", q.kind);
  if (q.orgType) query.set("org_type", q.orgType);
  if (q.organization) query.set("organization_id", q.organization);
  if (q.bdm) query.set("bdm_user_id", q.bdm);
  return `${TASKS_URL}?${query}`;
}

export const orgTasksUrl = (orgId: string) => tasksUrl({ bucket: "open", organization: orgId });

export function isTask(data: unknown): data is Task {
  const d = data as Partial<Task> | null;
  return !!d && typeof d.id === "string" && typeof d.title === "string" && typeof d.due_on === "string" && !!d.permissions;
}

export function isTaskPage(data: unknown): data is TaskPage {
  if (!isPage(data)) return false;
  const counts = (data as { counts?: { by_org_type?: unknown } }).counts;
  return !!counts && Array.isArray(counts.by_org_type);
}

export const orgTypeText = (t: OrgType | null) => (t ? ORG_TYPE_LABEL[t] : "No organization");

/** The API answers its date and organization rules as one sentence; put each on the field it is about. */
export function taskRuleField(detail: unknown): Record<string, string> {
  if (typeof detail !== "string") return {};
  if (detail.startsWith("Due date")) return { due_on: detail };
  if (detail.startsWith("This organization") || detail.startsWith("Only the assigned BDM can add")) return { organization_id: detail };
  return {};
}

export function daysOverdue(due: string, today: string): number {
  return Math.round((Date.parse(`${today}T00:00:00Z`) - Date.parse(`${due}T00:00:00Z`)) / 86_400_000);
}

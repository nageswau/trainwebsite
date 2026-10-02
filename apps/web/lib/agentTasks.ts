// AGN-016 (DEC-SCOPE-051): an agency's tasks and follow-ups -- the shapes, views and form rules the Tasks page, the student card and
// the form share. The server is the authority (scope, closed and archived refusals, the application rule); these only keep the
// screens from sending what it would refuse.

export const TASKS_URL = "/api/v1/workflows/overseas/agent/crm/tasks";
export const PAGE_SIZE = 20;
export const TITLE_MAX = 200;
export const NOTES_MAX = 2000;

export const TASK_VIEWS = ["open", "overdue", "done", "cancelled", "all"] as const;
export type TaskView = (typeof TASK_VIEWS)[number];
export const VIEW_LABELS: Record<TaskView, string> = { open: "Open", overdue: "Overdue", done: "Done", cancelled: "Cancelled", all: "All" };
export const EMPTY_TEXT: Record<TaskView, string> = {
  open: "No open tasks.",
  overdue: "Nothing overdue.",
  done: "No completed tasks yet.",
  cancelled: "No cancelled tasks.",
  all: "No tasks yet.",
};

export function parseView(value: string | null | undefined): TaskView {
  return (TASK_VIEWS as readonly string[]).includes(value ?? "") ? (value as TaskView) : "open";
}

export type AgentTask = {
  id: string;
  title: string;
  notes: string | null;
  due_at: string;
  status: "open" | "done" | "cancelled";
  overdue: boolean;
  student: { id: string; full_name: string; status: string };
  application: { id: string; university: string | null } | null;
  assigned_to: { code: string; full_name: string; status: string } | null;
  created_by: string | null;
  closed_by: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TaskDraft = { studentId: string; title: string; dueLocal: string; notes: string; applicationId: string };
export type DraftField = "studentId" | "title" | "dueLocal" | "notes";

export const emptyDraft = (studentId = ""): TaskDraft => ({ studentId, title: "", dueLocal: "", notes: "", applicationId: "" });

const pad = (n: number) => String(n).padStart(2, "0");

// The browser's own clock: a datetime-local value has no zone, so it is read as the viewer's local time and sent as an instant (UTC,
// "Z") -- the server refuses a time without an offset rather than guess.
export function toLocalInput(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function localToIso(local: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local)) return null;
  const d = new Date(local);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function isPastLocal(local: string, now: Date = new Date()): boolean {
  const iso = localToIso(local);
  return iso !== null && Date.parse(iso) < now.getTime();
}

export function validateDraft(d: TaskDraft): Partial<Record<DraftField, string>> {
  const errors: Partial<Record<DraftField, string>> = {};
  if (!d.studentId) errors.studentId = "Choose a student.";
  const title = d.title.trim();
  if (!title) errors.title = "Title is required.";
  else if (title.length > TITLE_MAX) errors.title = `Title must be ${TITLE_MAX} characters or fewer.`;
  if (!localToIso(d.dueLocal)) errors.dueLocal = "Choose a due date and time.";
  if (d.notes.trim().length > NOTES_MAX) errors.notes = `Notes must be ${NOTES_MAX} characters or fewer.`;
  return errors;
}

export function buildCreatePayload(d: TaskDraft): Record<string, unknown> {
  return { agent_student_id: d.studentId, title: d.title.trim(), due_at: localToIso(d.dueLocal), notes: d.notes.trim() || null, application_id: d.applicationId || null };
}

export function draftFromTask(t: AgentTask): TaskDraft {
  return { studentId: t.student.id, title: t.title, dueLocal: toLocalInput(t.due_at), notes: t.notes ?? "", applicationId: t.application?.id ?? "" };
}

// Only what changed, so an untouched field never becomes an audited edit. The due time is compared to the minute the input shows.
export function buildUpdatePayload(d: TaskDraft, original: AgentTask): Record<string, unknown> {
  const before = draftFromTask(original);
  const payload: Record<string, unknown> = {};
  if (d.title.trim() !== before.title) payload.title = d.title.trim();
  if (d.dueLocal !== before.dueLocal) payload.due_at = localToIso(d.dueLocal);
  if (d.notes.trim() !== before.notes) payload.notes = d.notes.trim() || null;
  if (d.applicationId !== before.applicationId) payload.application_id = d.applicationId || null;
  return payload;
}

export const taskUrl = (id: string) => `${TASKS_URL}/${id}`;

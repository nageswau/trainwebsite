// hrc-016 (DEC-SCOPE-387): a candidate's private notes and tasks, and "My tasks" -- types, labels and endpoints. The API decides who reads
// and writes (candidate readers / writers) and every rule (future due time, an active assignee, the candidate's own application); the UI
// only offers what `can_change` allows.
import { isPage, type Page } from "@/lib/apiErrors";
import { type OwnerRef, candidateUrl } from "@/lib/recruiterCandidates";
import type { Due } from "@/lib/recruiterFollowUps";

export const NOTE_MAX = 2000;
export const TITLE_MAX = 200;
export const LIST_LIMIT = 50;
export const PRIVATE_HINT = "Private to the recruitment team — never shown to candidates or employers.";

/** T3: the PDF §12 task kinds, in source order. */
export const TASK_TYPES = [
  { key: "follow_up", label: "Follow-up" },
  { key: "resume_screening", label: "Resume screening" },
  { key: "interview_coordination", label: "Interview coordination" },
  { key: "employer_feedback", label: "Employer feedback" },
] as const;
export type TaskType = (typeof TASK_TYPES)[number]["key"];
const TYPE_LABEL: Record<string, string> = Object.fromEntries(TASK_TYPES.map((t) => [t.key, t.label]));
export const taskTypeLabel = (key: string | null | undefined) => (key ? TYPE_LABEL[key] ?? key : "");

type PersonRef = { id: string; full_name: string };
export type CandidateNote = { id: string; body: string; author: PersonRef | null; created_at: string };
export type CandidateTask = {
  id: string; task_type: TaskType; title: string; notes: string | null; due_at: string; status: "open" | "done" | "cancelled"; overdue: boolean;
  assignee: OwnerRef; candidate: { id: string; candidate_code: string; name: string }; application_id: string | null;
  requirement: { id: string; code: string | null; title: string } | null; created_by: PersonRef; created_at: string;
  completed_at: string | null; completed_by: PersonRef | null; cancelled_at: string | null; cancelled_by: PersonRef | null; can_change: boolean;
};
export type TaskListPage = Page<CandidateTask> & { day: string; counts: Record<Due, number> };

export const TASKS_URL = "/api/v1/recruiter/candidate-tasks";
export const TASKS_PATH = "/recruiter/tasks";
export const notesUrl = (candidateId: string, offset = 0) => `${candidateUrl(candidateId, "/notes")}?limit=${LIST_LIMIT}&offset=${offset}`;
export const candidateTasksUrl = (candidateId: string, offset = 0) => `${candidateUrl(candidateId, "/tasks")}?limit=${LIST_LIMIT}&offset=${offset}`;
export const newTaskUrl = (candidateId: string) => candidateUrl(candidateId, "/tasks");
export const newNoteUrl = (candidateId: string) => candidateUrl(candidateId, "/notes");
export const taskUrl = (id: string, action?: "complete" | "cancel") => `${TASKS_URL}/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;
export const myTasksUrl = (due: Due, offset = 0) => `${TASKS_URL}?${new URLSearchParams({ due, limit: String(LIST_LIMIT), offset: String(offset) })}`;
export const candidateApplicationsUrl = (candidateId: string) => candidateUrl(candidateId, "/applications");

const ROLE: Record<string, string> = { placement_team: "Recruiter", placement_manager: "Placement manager", super_admin: "Super admin" };

/** The assignee picker's server search (SearchableSelect): active people who may be given a task, names and roles only. */
export async function taskAssigneeSearch(q: string, signal: AbortSignal) {
  const response = await fetch(`${TASKS_URL}/assignees${q ? `?${new URLSearchParams({ q })}` : ""}`, { signal });
  if (!response.ok) throw new Error(`Assignee search failed (${response.status})`);
  const people = (await response.json()) as { id: string; full_name: string; role: string }[];
  return { items: people.map((p) => ({ id: p.id, label: p.full_name, detail: ROLE[p.role] ?? null })), truncated: false };
}

export function isCandidateTask(data: unknown): data is CandidateTask {
  const d = data as Partial<CandidateTask> | null;
  return !!d && typeof d.id === "string" && typeof d.due_at === "string" && !!d.assignee && typeof d.can_change === "boolean";
}

export function isCandidateNote(data: unknown): data is CandidateNote {
  const d = data as Partial<CandidateNote> | null;
  return !!d && typeof d.id === "string" && typeof d.body === "string" && typeof d.created_at === "string";
}

export function isTaskListPage(data: unknown): data is TaskListPage {
  return isPage(data) && typeof (data as { day?: unknown }).day === "string" && !!(data as { counts?: unknown }).counts;
}

// itc-027 (DEC-SCOPE-353): the HR resume-review task -- types, labels and endpoints for HR's queue and task, the IT Admin's task list
// and rules, the counselor / IT Admin read-only card and the student's safe status. The API decides who sees what (API_CONTRACT §12IY).

export const HR_REVIEW_STAGES = ["resume_received", "under_review", "changes_requested", "screening", "interview_ready", "completed", "withdrawn"] as const;
export type HrReviewStage = (typeof HR_REVIEW_STAGES)[number];
export const OPEN_STAGES: HrReviewStage[] = ["resume_received", "under_review", "changes_requested", "screening", "interview_ready"];
/** The stages HR may choose (`withdrawn` is set by the system when the student leaves placement). */
export const HR_SETTABLE_STAGES: HrReviewStage[] = [...OPEN_STAGES, "completed"];

export const STAGE_LABELS: Record<HrReviewStage, string> = {
  resume_received: "Resume received", under_review: "Under review", changes_requested: "Changes requested", screening: "Screening",
  interview_ready: "Interview ready", completed: "Completed", withdrawn: "Withdrawn",
};

export const CHECKLIST_ITEMS = [
  { key: "contact", label: "Contact details are complete" },
  { key: "education", label: "Education is listed" },
  { key: "skills", label: "Skills match the course" },
  { key: "projects", label: "Projects or experience are described" },
  { key: "formatting", label: "Formatting and spelling are clean" },
] as const;
export type ChecklistKey = (typeof CHECKLIST_ITEMS)[number]["key"];

export type Owner = { id: string; full_name: string; active: boolean };
export type HrReviewSummary = {
  id: string; student: { id: string; full_name: string; student_code: string | null }; owner: Owner | null; stage: HrReviewStage;
  stage_label: string; resume_version: number; screening_date: string | null; assigned_at: string | null; closed_at: string | null; updated_at: string;
};
export type HrReviewHistory = { from_stage: HrReviewStage | null; to_stage: HrReviewStage; reason: string; actor: string | null; created_at: string };
export type HrReviewTask = HrReviewSummary & {
  role_preferences: string | null; skill_gap_notes: string | null; checklist: ChecklistKey[]; history: HrReviewHistory[];
};
export type HrReviewPage = { items: HrReviewSummary[]; total: number; limit: number; offset: number };
export type HrQueue = HrReviewPage & { counts: Record<HrReviewStage, number> };
export type StaffReview = {
  task: { stage: HrReviewStage; stage_label: string; owner: { full_name: string } | null; next_action: string; screening_date: string | null;
    resume_version: number; closed: boolean; updated_at: string } | null;
};
export type StudentReview = { status: { label: string; action: string | null; updated_at: string | null } | null };
export type HrRule = { program_id: string; program: string; active: boolean; hr_user: Owner | null };
export type HrRules = { programs: HrRule[]; hr_users: { id: string; full_name: string }[] };

export const PAGE_SIZE = 25;
export const HR_QUEUE_API = "/api/v1/hr/review-tasks";
export const HR_QUEUE_PATH = "/it/hr/queue";
export const ADMIN_TASKS_API = "/api/v1/admin/it/hr-review-tasks";
export const ADMIN_RULES_API = "/api/v1/admin/it/hr-assignment-rules";
export const MY_REVIEW_API = "/api/v1/it/me/hr-review";
export const hrTaskUrl = (studentId: string) => `/api/v1/hr/students/${encodeURIComponent(studentId)}/review`;
export const ownerUrl = (taskId: string) => `${ADMIN_TASKS_API}/${encodeURIComponent(taskId)}/owner`;
export const ruleUrl = (programId: string) => `${ADMIN_RULES_API}/${encodeURIComponent(programId)}`;
export const staffReviewUrl = (portal: "counselor" | "admin", studentId: string) =>
  `/api/v1/${portal}/it/students/${encodeURIComponent(studentId)}/hr-review`;

/** `?stage=…&page=…` for a list page (page 1 and no stage are left out). */
export function listQuery(params: { stage?: string; page?: number }): string {
  const q = new URLSearchParams();
  if (params.stage) q.set("stage", params.stage);
  if (params.page && params.page > 1) q.set("page", String(params.page));
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** The API's `limit`/`offset` for a 1-based page, plus the filters. */
export function apiQuery(params: { stage?: string; page: number; unassigned?: boolean }): string {
  const q = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String((params.page - 1) * PAGE_SIZE) });
  if (params.stage) q.set("stage", params.stage);
  if (params.unassigned) q.set("unassigned", "true");
  return `?${q.toString()}`;
}

export const isStage = (value: unknown): value is HrReviewStage => typeof value === "string" && (HR_REVIEW_STAGES as readonly string[]).includes(value);

/** A day in IST (a date-only value is UTC midnight, which is the same day in IST). */
export function formatDay(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });
}

// itc-022 (DEC-SCOPE-365): programme progress plans (the IT Admin), topic completion (trainer), the computed progress %, remediation plans
// and the student's progress view. API_CONTRACT §12JK.

export const PROGRESS_PLANS_URL = "/api/v1/admin/it/progress-plans";
export const progressPlanUrl = (programId: string) => `${PROGRESS_PLANS_URL}/${encodeURIComponent(programId)}`;
export const batchTopicsUrl = (batchId: string) => `/api/v1/it/batches/${encodeURIComponent(batchId)}/topics`;
export const topicCompletionsUrl = (batchId: string, topicId: string) => `${batchTopicsUrl(batchId)}/${encodeURIComponent(topicId)}/completions`;
export const studentPlansUrl = (studentId: string) => `/api/v1/it/students/${encodeURIComponent(studentId)}/remediation-plans`;
export const enrollmentPlansUrl = (enrollmentId: string) => `/api/v1/it/enrollments/${encodeURIComponent(enrollmentId)}/remediation-plans`;
export const planUrl = (planId: string) => `/api/v1/it/remediation-plans/${encodeURIComponent(planId)}`;
export const progressOverrideUrl = (enrollmentId: string) => `/api/v1/workflows/it/trainer/enrollments/${encodeURIComponent(enrollmentId)}/progress`;
export const MY_PROGRESS_URL = "/api/v1/it/me/progress";

export type Weights = { topics: number; assignments: number; assessments: number };
export type PlanTopic = { id?: string; title: string };
export type PlanModule = { id?: string; title: string; topics: PlanTopic[] };
export type PlanSummary = { program_id: string; program: string; active: boolean; modules: number; topics: number; weights: Weights | null; computed: boolean };
export type Plan = { program_id: string; program: string; modules: PlanModule[]; weights: Weights | null; computed: boolean; copy_source: { title: string; topics: string[] }[] };

export type BatchTopic = { id: string; title: string; completed_enrollment_ids: string[] };
export type BatchTopics = { batch_id: string; computed: boolean; modules: { id: string; title: string; topics: BatchTopic[] }[] };

export type PlanStatus = "open" | "in_progress" | "completed" | "cancelled";
export type RemediationPlan = {
  id: string;
  actions: string;
  due_date: string;
  status: PlanStatus;
  owner_name: string | null;
  batch: string;
  owner_user_id?: string;
  enrollment_id?: string;
  risk_flag_id?: string | null;
};
export type StudentPlans = {
  student: { id: string; full_name: string; student_code: string | null };
  items: RemediationPlan[];
  enrollments: { enrollment_id: string; batch: string }[];
  owner_options: { id: string; name: string; role: string }[];
  viewer_id: string;
};

export type MyCourse = {
  enrollment_id: string;
  course: string;
  batch: string;
  status: string;
  progress_percent: number;
  mode: "computed" | "manual" | "override";
  weights: Weights | null;
  topics_completed: number;
  topics_total: number;
  labs_graded: number;
  labs_total: number;
  assignments_graded: number;
  assignments_total: number;
  assessments_passed: number;
  assessments_total: number;
  modules: { title: string; topics: { title: string; completed: boolean }[] }[];
};
export type MyProgress = { courses: MyCourse[]; remediation_plans: RemediationPlan[] };

export const STATUS_LABEL: Record<PlanStatus, string> = { open: "Open", in_progress: "In progress", completed: "Completed", cancelled: "Cancelled" };
export const CLOSED: PlanStatus[] = ["completed", "cancelled"];

export const weightTotal = (w: Weights) => w.topics + w.assignments + w.assessments;

/** P3 in words, e.g. "Topics 50% · Assignments 30% · Assessments 20%" (a zero weight is left out). */
export function weightsSummary(w: Weights | null): string {
  if (!w) return "Set by the trainer";
  const parts: [string, number][] = [["Topics", w.topics], ["Assignments", w.assignments], ["Assessments", w.assessments]];
  return parts.filter(([, value]) => value > 0).map(([name, value]) => `${name} ${value}%`).join(" · ");
}

/** P1: what "Copy from syllabus" puts in the editor -- new modules/topics (no ids), blank titles dropped. */
export function fromCopySource(source: Plan["copy_source"]): PlanModule[] {
  return source.filter(m => m.title.trim()).map(m => ({ title: m.title.trim(), topics: m.topics.filter(t => t.trim()).map(t => ({ title: t.trim() })) }));
}

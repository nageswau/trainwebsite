import { isCalendarDate } from "@/lib/formatDate";

// mgmt-017 (EVID-017 §12, spec TR1-TR16): GET /management/training -- the 11 Training KPIs and every trainer's figures for an IST
// period. The API decides access and every figure; a share or average is null when there is nothing to divide.
export const TRAINING_HOME = "/management/training";
export const TRAINING_API = "/api/v1/management/training";

export type TrainingKpiKey =
  | "total_courses" | "active_batches" | "students" | "trainers" | "attendance_pct" | "completion_pct" | "dropouts" | "assessments"
  | "certifications" | "placement_ready" | "placements"; // prettier-ignore
export type TrainingKpi = { key: TrainingKpiKey; label: string; definition: string; value: number | null };
export type TrainerFigureKey = "students_trained" | "attendance_pct" | "completion_pct" | "feedback_avg" | "assessment_pass_pct" | "batch_performance" | "placements";
export type TrainerFigure = { key: TrainerFigureKey; label: string; definition: string };
export type TrainerRow = {
  id: string; full_name: string; active: boolean; batches: number; students_trained: number; attendance_pct: number | null;
  completion_pct: number | null; feedback_avg: number | null; feedback_count: number; assessment_pass_pct: number | null;
  batch_performance: number | null; placements: number;
}; // prettier-ignore
export type TrainingDashboard = { from: string; to: string; as_of: string; kpis: TrainingKpi[]; trainer_figures: TrainerFigure[]; trainers: TrainerRow[] };
export type TrainingQuery = { from: string; to: string };

/** The page's address: an impossible date or a repeated value is dropped, so the API answers with this month. */
export function trainingQuery(search: Record<string, string | string[] | undefined>): TrainingQuery {
  const day = (key: string) => (typeof search[key] === "string" && isCalendarDate(search[key] as string) ? (search[key] as string) : "");
  return { from: day("from"), to: day("to") };
}

export function trainingUrl({ from, to }: TrainingQuery): string {
  const params = new URLSearchParams({ ...(from ? { from } : {}), ...(to ? { to } : {}) }).toString();
  return params ? `${TRAINING_API}?${params}` : TRAINING_API;
}

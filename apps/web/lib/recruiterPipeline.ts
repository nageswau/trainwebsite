// rec-005 (DEC-SCOPE-123): the company B2B pipeline. The API owns the catalogue (labels, kinds and states come with every company) and every
// rule; these helpers only shape requests and read responses. Conflict and 422 readers are bdm-004's (`lib/bdmPipeline`).
import type { Person } from "@/lib/recruiterCompanies";

export type StageKind = "start" | "manual" | "driven";
export type PipelineStep = { key: string; label: string; kind: StageKind; state: "done" | "current" | "upcoming" };
export type Pipeline = {
  stage: string; stage_label: string; stage_changed_at: string; lost: { at: string; reason: string } | null; can_move: boolean;
  can_reopen: boolean; steps: PipelineStep[];
};
export type StageEvent = {
  id: string; event: string; from_stage: string; from_label: string; to_stage: string; to_label: string; reason: string | null;
  actor: { id: string; full_name: string } | null; created_at: string;
};
export type BoardItem = {
  id: string; code: string; name: string; city: string | null; priority: string | null; assigned_recruiter: Person | null; stage: string;
  stage_label: string; lost: boolean;
};
export type BoardView = { stages: { key: string; label: string; kind: StageKind; count: number }[]; lost_count: number; items: BoardItem[]; total: number; limit: number; offset: number };

export const PIPELINE_PATH = "/recruiter/pipeline";
export const BOARD_URL = "/api/v1/recruiter/pipeline";
export const LOST = "lost";
export const HISTORY_PAGE = 20;
export const STATE_TEXT: Record<PipelineStep["state"], string> = { done: "Done", current: "Current", upcoming: "Upcoming" };

export const companyActionUrl = (companyId: string, action: "stage" | "lost" | "reopen") => `/api/v1/recruiter/companies/${companyId}/${action}`;
export const historyUrl = (companyId: string, offset = 0) => `/api/v1/recruiter/companies/${companyId}/stage-history?limit=${HISTORY_PAGE}&offset=${offset}`;

/** Moving to an earlier stage needs a reason. */
export function isBackward(p: Pipeline, to: string): boolean {
  const keys = p.steps.map((s) => s.key);
  return keys.indexOf(to) < keys.indexOf(p.stage);
}

/** The 409 for a Lost flag someone else changed (`company_lost` / `company_not_lost`): its message, else null. */
export function lostConflict(detail: unknown): string | null {
  const d = detail as { code?: unknown; message?: unknown } | null;
  const lost = d && typeof d === "object" && (d.code === "company_lost" || d.code === "company_not_lost");
  return lost && typeof d.message === "string" ? d.message : null;
}

/** How a history row names who changed it: a person, or the requirement event that moved it. */
export function changedBy(e: StageEvent): string {
  return e.actor ? `By ${e.actor.full_name}` : `By the system (${e.event.replaceAll("_", " ")})`;
}

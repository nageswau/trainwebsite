import { detailMessage } from "@/lib/apiErrors";
import { type BdmType, PAGE_SIZE } from "@/lib/bdm";
import { ORGS_URL, type OrgPerson, type OrgType } from "@/lib/bdmOrganizations";

// bdm-004 (DEC-SCOPE-070): the organization pipeline. The API owns the catalogue (labels, kinds, states come with every organization)
// and every rule; these helpers only shape requests and read responses.
export type StepKind = "manual" | "live" | "volume";
export type StepState = "done" | "current" | "upcoming" | "awaiting_handover" | "not_tracked";
export type PipelineStep = { key: string; label: string; kind: StepKind; state: StepState };
export type Pipeline = { stage: string; stage_label: string; lost: { at: string; reason: string } | null; agent_status: string | null; steps: PipelineStep[] };
export type StageEvent = {
  id: string; kind: "move" | "lost" | "revived"; from_stage: string; from_label: string; to_stage: string; to_label: string;
  note: string | null; actor: { id: string; full_name: string }; created_at: string;
};
export type StageCount = { key: string; label: string; kind: StepKind; count: number | null };
export type PipelineItem = { id: string; code: string; name: string; city: string; org_type: OrgType; assigned_bdm: OrgPerson; stage: string; stage_label: string; lost: boolean };
export type PipelineView = { bdm_type: BdmType; stages: StageCount[]; lost_count: number; items: PipelineItem[]; total: number; limit: number; offset: number };
export type PipelineParams = { bdm_type?: BdmType; assigned?: string; stage?: string; offset?: number };

export const PIPELINE_URL = "/api/v1/bdm/pipeline";
export const LOST = "lost";
export const HISTORY_PAGE = 20;
export const STATE_TEXT: Record<StepState, string> = {
  done: "Done", current: "Current", upcoming: "Upcoming", awaiting_handover: "Awaiting handover", not_tracked: "Not tracked",
};

export const orgActionUrl = (orgId: string, action: "stage" | "lost" | "revive") => `${ORGS_URL}/${orgId}/${action}`;
export const historyUrl = (orgId: string, offset = 0) => `${ORGS_URL}/${orgId}/stage-history?limit=${HISTORY_PAGE}&offset=${offset}`;

/** S6: moving to an earlier stage needs a note. */
export function isBackward(p: Pipeline, to: string): boolean {
  const keys = p.steps.map((s) => s.key);
  return keys.indexOf(to) < keys.indexOf(p.stage);
}

/** The 409 `stage_changed` body names the stage someone else moved the organization to. */
export function stageChanged(detail: unknown): string | null {
  const d = detail as { code?: unknown; current_stage?: unknown } | null;
  return d && typeof d === "object" && d.code === "stage_changed" && typeof d.current_stage === "string" ? d.current_stage : null;
}

/** The 409 for a Lost flag someone else changed (`organization_lost` / `organization_not_lost`): its message, else null. */
export function lostConflict(detail: unknown): string | null {
  const d = detail as { code?: unknown; message?: unknown } | null;
  const lost = d && typeof d === "object" && (d.code === "organization_lost" || d.code === "organization_not_lost");
  return lost && typeof d.message === "string" ? d.message : null;
}

/** FastAPI's 422 list as {field: message}, worded by detailMessage (no "Value error," prefix). */
export function fieldErrors(detail: unknown): Record<string, string> {
  if (!Array.isArray(detail)) return {};
  return Object.fromEntries(detail.map((d: { loc?: unknown[] }) => [String(d?.loc?.at(-1) ?? ""), detailMessage([d])]));
}

export function pipelineQuery(params: PipelineParams): string {
  const q = new URLSearchParams();
  if (params.bdm_type) q.set("bdm_type", params.bdm_type);
  if (params.assigned) q.set("assigned", params.assigned);
  if (params.stage) q.set("stage", params.stage);
  q.set("limit", String(PAGE_SIZE));
  q.set("offset", String(params.offset ?? 0));
  return q.toString();
}

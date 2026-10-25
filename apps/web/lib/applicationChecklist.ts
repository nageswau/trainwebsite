// ccrm-019 (DEC-SCOPE-257): an application's document checklist. The server (api/application_checklists.py) is the authority on
// every rule -- item status (AC1), the summary, the completion date and the Ready-for-Submission gate; this only shapes the responses.
import type { GateMode, Sensitivity } from "@/lib/documentChecklists";

export const checklistUrl = (applicationId: string) => `/api/v1/workflows/overseas/applications/${applicationId}/checklist`;

export type ChecklistDocument = { id: string; document_type: string; document_label: string | null; original_filename: string | null; verification_status: string; status_label: string; created_at: string; sensitivity: Sensitivity };
export type ChecklistMark = "requested" | "not_required";
export type ApplicationChecklistItem = {
  id: string;
  position: number;
  document_type: string;
  label: string | null;
  name: string;
  required: boolean;
  notes: string | null;
  allowed_statuses: string[];
  mark: ChecklistMark | null;
  status: string;
  status_label: string;
  removable: boolean;
  sensitivity: Sensitivity; // ccrm-022 (DEC-SCOPE-262 SD2)
  documents: ChecklistDocument[];
};
export type MissingItem = { id: string; label: string; status: string; status_label: string };
export type ChecklistSummary = { required_total: number; required_complete: number; optional_total: number; optional_complete: number; ready: boolean; missing: MissingItem[] };
export type ApplicationChecklist = {
  template_id: string | null;
  template_version: number | null;
  gate_mode: GateMode;
  documents_completed_on: string | null;
  summary: ChecklistSummary;
  items: ApplicationChecklistItem[];
};
export type ChecklistPayload = {
  checklist: ApplicationChecklist | null;
  template: { id: string; name: string; version: number; gate_mode: GateMode } | null;
  documents: ChecklistDocument[];
};

/** Complete statuses (app/application_checklists.COMPLETE). */
export const COMPLETE = new Set(["verified", "approved", "not_required"]);

/** The sub-status route's 409 detail when the checklist gate refuses Ready for Submission. */
export type GateRefusal = { message: string; gate_mode: GateMode; missing: MissingItem[] };
export function gateRefusal(detail: unknown): GateRefusal | null {
  const d = detail as Partial<GateRefusal> | null;
  return d && typeof d === "object" && typeof d.message === "string" && Array.isArray(d.missing) ? (d as GateRefusal) : null;
}

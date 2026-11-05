// hrc-004 (DEC-SCOPE-376 B6): a job requirement's or a candidate's change history -- GET /recruiter/{requirements|candidates}/{id}/history.
import type { AuditChanges } from "@/lib/auditLog";

export const HISTORY_PAGE_SIZE = 20;

export type HistoryItem = {
  id: string; action: string; created_at: string; actor: { id: string; full_name: string } | null;
  changes: AuditChanges | null; fields: string[] | null;
};
export type HistoryPage = { items: HistoryItem[]; total: number; limit: number; offset: number };

export const historyPageUrl = (url: string, offset: number) => `${url}?limit=${HISTORY_PAGE_SIZE}&offset=${offset}`;

export const isHistoryPage = (body: unknown): body is HistoryPage =>
  typeof body === "object" && body !== null && Array.isArray((body as HistoryPage).items) && typeof (body as HistoryPage).total === "number";

// pob-002 (QA-01): field names whose plain humanised form reads badly
const FIELD_WORDS: Record<string, string> = {
  expected_tat_days: "Expected turnaround (days)", payment_days: "Payment due (days after joining)", decision_maker_contact: "Decision-maker",
};

/** "salary_min" → "Salary min", "on_hold" → "On hold", "source_id" → "Source" (QA-02). */
export const humanise = (key: string) => FIELD_WORDS[key] ?? (key.charAt(0).toUpperCase() + key.slice(1)).replace(/_id$/, "").replace(/_/g, " ");

const ACTIONS: Record<string, string> = {
  "recruiter_requirement.create": "Created",
  "recruiter_requirement.update": "Details edited",
  "recruiter_requirement.status": "Status changed",
  "recruiter_requirement.assign": "Recruiter changed",
  "recruiter_requirement.weights": "Skill weights changed",
  "recruiter_requirement.duplicate_override": "Saved despite a possible duplicate", // hrc-005
  "recruiter_requirement.owner_added": "Owner added", // hrc-006
  "recruiter_requirement.owner_removed": "Owner removed",
  "recruiter_requirement.backup_released": "Backup owner removed (user deactivated)", // pob-002
  "job_description.create": "JD version saved",
  "job_description.upload": "JD file uploaded",
  "candidate.create": "Created",
  "candidate.update": "Profile edited",
  "candidate.archive": "Archived",
  "candidate.restore": "Restored",
  "candidate.resume_upload": "Resume uploaded",
  "candidate.resume_extract": "Skills read from the resume",
  "candidate.skill_add": "Skill added",
  "candidate.skill_update": "Skill edited",
  "candidate.skill_remove": "Skill removed",
  "candidate.skill_status": "Skill status changed",
  "candidate.document_upload": "Document uploaded", // hrc-015
  "candidate.document_request": "Document requested",
  "candidate.document_request_cancel": "Document request cancelled",
};

/** A known action's words; any other as its last part, humanised (a new action never shows a raw key). */
export const actionLabel = (action: string) => ACTIONS[action] ?? humanise(action.slice(action.lastIndexOf(".") + 1));

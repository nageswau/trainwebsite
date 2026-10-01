// ENH-020 (DEC-SCOPE-043): one source for the funding support case lifecycle and labels, used by the form, the counsellor's list and
// every read-only view. The stage table mirrors the API's (schemas.FUNDING_STATUS_NEXT); the API still decides.
export type FundingSupportType = "education_loan" | "financial_assistance" | "scholarship" | "funding_guidance";
export type FundingStatus = "required" | "counselling" | "documents" | "application" | "approved" | "completed" | "closed";

export type FundingRecord = {
  id: string; school_student_id: string; support_type: FundingSupportType; status: FundingStatus; status_changed_on: string;
  provider_name: string | null; amount_text: string | null; notes: string; closure_reason: string | null;
  created_at: string; updated_at: string; counselor_name: string | null; updated_by_name: string | null;
};

export const FUNDING_STATUSES: FundingStatus[] = ["required", "counselling", "documents", "application", "approved", "completed", "closed"];
export const SUPPORT_TYPE_LABEL: Record<FundingSupportType, string> = {
  education_loan: "Education loan", financial_assistance: "Financial assistance", scholarship: "Scholarship", funding_guidance: "Funding guidance",
};
export const STATUS_LABEL: Record<FundingStatus, string> = {
  required: "Required", counselling: "Counselling", documents: "Documents", application: "Application", approved: "Approved", completed: "Completed", closed: "Closed",
};
export const TEXT_LIMITS = { provider_name: 200, amount_text: 120, closure_reason: 500, notes: 4000 } as const;

const SOURCE_STAGES: FundingStatus[] = ["required", "counselling", "documents", "application", "approved", "completed"];

export function isFinal(status: FundingStatus): boolean {
  return status === "completed" || status === "closed";
}

/** The stages the API accepts from here: the next source stage and Closed, or nothing once the case is final. */
export function nextStatuses(status: FundingStatus): FundingStatus[] {
  if (isFinal(status)) return [];
  return [SOURCE_STAGES[SOURCE_STAGES.indexOf(status) + 1], "closed"];
}

/** A stage in words, never colour alone: "Stage 3 of 6 · Documents"; Closed is outside the six source stages. */
export function stageText(status: FundingStatus): string {
  if (status === "closed") return STATUS_LABEL.closed;
  return `Stage ${SOURCE_STAGES.indexOf(status) + 1} of ${SOURCE_STAGES.length} · ${STATUS_LABEL[status]}`;
}

/** The status pill's tone: open stages are pending, Approved/Completed are good news, Closed is neutral (it carries its word). */
export function statusClass(status: FundingStatus): string {
  if (status === "approved" || status === "completed") return "status";
  if (status === "closed") return "status closed";
  return "status pending";
}

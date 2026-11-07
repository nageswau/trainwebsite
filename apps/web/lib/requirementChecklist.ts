// pob-016 (DEC-SCOPE-419): a requirement's validation checklist -- types, labels and endpoints. The API owns the items and decides every rule; the card only renders them.
import { REQUIREMENTS_URL } from "@/lib/recruiterRequirements";

export type ItemStatus = "confirmed" | "not_applicable" | "missing";
export type ChecklistItem = {
  key: string; label: string; hint: string; status: ItemStatus | null;
  follow_up: { id: string; status: "open" | "done" | "cancelled"; due_at: string; contact: string | null } | null;
};
export type Checklist = {
  items: ChecklistItem[];
  summary: { total: number; confirmed: number; not_applicable: number; missing: number; not_reviewed: number; complete: boolean };
  blocking: { on: boolean; company_rule: boolean | null; global_rule: boolean };
  override: { reason: string; by: { id: string; full_name: string; active: boolean } | null; at: string } | null;
  sourcing_started: boolean; warning: string | null; company_id: string;
  can_edit: boolean; can_override: boolean; can_set_company_rule: boolean; can_set_global_rule: boolean;
};

export const ITEM_STATUSES: { key: ItemStatus; label: string }[] = [
  { key: "confirmed", label: "Confirmed" },
  { key: "not_applicable", label: "Not applicable" },
  { key: "missing", label: "Missing" },
];
export const NOT_REVIEWED = "Not reviewed";
export const statusLabel = (status: ItemStatus | null) => ITEM_STATUSES.find((s) => s.key === status)?.label ?? NOT_REVIEWED;
export const OVERRIDE_REASON_MAX = 500;

export const checklistUrl = (requirementId: string) => `${REQUIREMENTS_URL}/${encodeURIComponent(requirementId)}/checklist`;
export const companyRuleUrl = (companyId: string) => `/api/v1/recruiter/companies/${encodeURIComponent(companyId)}/checklist-rule`;
export const GLOBAL_RULE_URL = "/api/v1/recruiter/requirement-checklist/settings";

export const isChecklist = (body: unknown): body is Checklist => Array.isArray((body as Checklist | null)?.items) && typeof (body as Checklist).summary === "object";

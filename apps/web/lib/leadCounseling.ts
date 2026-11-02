// itc-010 (DEC-SCOPE-343): the IT counseling record -- one per session on a lead handed to an IT counselor; the telecaller side reads it.
// Types, labels, endpoints and the form <-> body mapping. The API decides scope and every rule (active IT course, active objections,
// dates today or later, closed lead 409).
import { counselorLeadUrl } from "@/lib/leadHandover";
import type { PersonRef } from "@/lib/telecallerLeads";

export const OUTCOMES = ["interested", "needs_time", "not_interested", "enrolled"] as const;
export const DECISION_MAKERS = ["self", "parent", "spouse", "employer", "other"] as const;
export const OUTCOME_LABEL: Record<string, string> = { interested: "Interested", needs_time: "Needs time", not_interested: "Not interested", enrolled: "Enrolled" };
export const DECISION_MAKER_LABEL: Record<string, string> = { self: "Self", parent: "Parent", spouse: "Spouse", employer: "Employer", other: "Other" };
export const NOTES_MAX = 4000;
export const OBJECTION_NOTES_MAX = 1000;
export const LIST_LIMIT = 50;
export const OBJECTIONS_URL = "/api/v1/telecaller/counseling-objections";

export type Ref = { id: string; name: string };
export type CounselingRecord = {
  id: string; recommended_product: Ref | null; objections: Ref[]; objection_notes: string | null; fee_quoted: string | null;
  expected_joining_date: string | null; decision_maker: string | null; outcome: string; next_follow_up: string | null; notes: string | null;
  author: PersonRef; updated_by: PersonRef; created_at: string; updated_at: string;
};
export type CounselingValues = {
  recommended_product_id: string; objection_ids: string[]; objection_notes: string; fee_quoted: string; expected_joining_date: string;
  decision_maker: string; outcome: string; next_follow_up: string; notes: string;
};

export const counselorCounselingUrl = (leadId: string, recordId?: string) => counselorLeadUrl(leadId, recordId ? `/counseling/${recordId}` : "/counseling");
export const telecallerCounselingUrl = (leadId: string) => `/api/v1/telecaller/leads/${encodeURIComponent(leadId)}/counseling`;
export const listUrl = (url: string) => `${url}?limit=${LIST_LIMIT}`;

export function counselingValues(record?: CounselingRecord): CounselingValues {
  return {
    recommended_product_id: record?.recommended_product?.id ?? "", objection_ids: record?.objections.map((o) => o.id) ?? [],
    objection_notes: record?.objection_notes ?? "", fee_quoted: record?.fee_quoted ?? "", expected_joining_date: record?.expected_joining_date ?? "",
    decision_maker: record?.decision_maker ?? "", outcome: record?.outcome ?? "", next_follow_up: record?.next_follow_up ?? "", notes: record?.notes ?? "",
  };
}

/** Every field is sent (an edit replaces them all; the API re-checks only what changed). Blank is null. */
export function counselingBody(v: CounselingValues): Record<string, unknown> {
  const blank = (s: string) => (s.trim() === "" ? null : s.trim());
  return {
    recommended_product_id: blank(v.recommended_product_id), objection_ids: v.objection_ids, objection_notes: blank(v.objection_notes),
    fee_quoted: blank(v.fee_quoted), expected_joining_date: blank(v.expected_joining_date), decision_maker: blank(v.decision_maker),
    outcome: v.outcome, next_follow_up: blank(v.next_follow_up), notes: blank(v.notes),
  };
}

export function isCounselingRecord(data: unknown): data is CounselingRecord {
  const d = data as Partial<CounselingRecord> | null;
  return !!d && typeof d.id === "string" && typeof d.outcome === "string" && Array.isArray(d.objections);
}

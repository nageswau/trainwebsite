// tel-018 (DEC-SCOPE-101, API §12V): the counselor handover, the counselor's leads, the return and the student link. Labels are display
// only; the API decides scope, `permissions` and every rule.
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import type { PersonRef, TelecallerLead } from "@/lib/telecallerLeads";

export type MilestoneKind = "enrollment" | "application" | "visa";
export type Milestone = { kind: MilestoneKind; label: string; status: string; reference: string | null; at: string };
export type Milestones = { student: { id: string; full_name: string; email: string } | null; items: Milestone[] };
export type CounselorLead = Omit<TelecallerLead, "read_only"> & {
  converted_user: (PersonRef & { email: string }) | null;
};
export type CounselorLeadDetail = CounselorLead & {
  message: string; milestones: Milestones;
  // ccrm-003 (DEC-SCOPE-243): the next action (a YYYY-MM-DD due date; overdue is the API's IST reading) and the stage / follow-up actions
  next_action: string | null; next_action_due: string | null; next_action_overdue: boolean;
  permissions: { return: boolean; link: boolean; unlink: boolean; stage: boolean; follow_up: boolean };
};
export type StudentSuggestion = { id: string; full_name: string; email: string; phone: string | null; linked_elsewhere: boolean };

export const COUNSELOR_LEADS_URL = "/api/v1/counselor/leads";
// csc-004 (DEC-SCOPE-229): an overseas counselor records a walk-in as a lead -- tel-005's intake (create, /duplicate-check,
// /{id}/enquiries) under the counselor's own prefix. A plain string: the server page hands it to the client NewLeadForm (QA-01).
export const WALK_IN_LEADS_URL = "/api/v1/counselor/walk-in-leads";
export const counselorLeadUrl = (id: string, suffix = "") => `${COUNSELOR_LEADS_URL}/${encodeURIComponent(id)}${suffix}`;
export const handoverUrl = (id: string) => `/api/v1/telecaller/leads/${encodeURIComponent(id)}/handover`;
/** ccrm-003 A1: the counselor's stage move (the next action is set on its own form first, so only the stage and reason go here). */
export const counselorMoveStage = (id: string, target: string, reason: string): Promise<SendOutcome> =>
  sendJson(counselorLeadUrl(id, "/stage"), "POST", reason ? { to_stage: target, reason } : { to_stage: target });
export const counselorLeadHref =(division: string, id: string) => `/${division === "overseas" ? "overseas" : "it"}/counselor/leads/${encodeURIComponent(id)}`;

const KIND_LABEL: Record<MilestoneKind, string> = { enrollment: "IT enrolment", application: "Overseas application", visa: "Visa case" };
export const milestoneKind = (kind: MilestoneKind) => KIND_LABEL[kind] ?? kind;
/** Status keys as stored, read aloud ("offer_received" -> "Offer received"). */
export const statusText = (status: string) => (status.charAt(0).toUpperCase() + status.slice(1)).replaceAll("_", " ");

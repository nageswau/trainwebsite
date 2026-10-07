// tel-018 (DEC-SCOPE-099, API §12T): the counselor handover, the counselor's leads, the return and the student link. Labels are display
// only; the API decides scope, `permissions` and every rule.
import type { PersonRef, TelecallerLead } from "@/lib/telecallerLeads";

export type MilestoneKind = "enrollment" | "application" | "visa";
export type Milestone = { kind: MilestoneKind; label: string; status: string; reference: string | null; at: string };
export type Milestones = { student: { id: string; full_name: string; email: string } | null; items: Milestone[] };
export type CounselorLead = Omit<TelecallerLead, "read_only"> & {
  converted_user: (PersonRef & { email: string }) | null;
};
export type CounselorLeadDetail = CounselorLead & {
  message: string; milestones: Milestones; permissions: { return: boolean; link: boolean; unlink: boolean };
};
export type StudentSuggestion = { id: string; full_name: string; email: string; phone: string | null; linked_elsewhere: boolean };

export const COUNSELOR_LEADS_URL = "/api/v1/counselor/leads";
export const counselorLeadUrl = (id: string, suffix = "") => `${COUNSELOR_LEADS_URL}/${encodeURIComponent(id)}${suffix}`;
export const handoverUrl = (id: string) => `/api/v1/telecaller/leads/${encodeURIComponent(id)}/handover`;
export const counselorLeadHref = (division: string, id: string) => `/${division === "overseas" ? "overseas" : "it"}/counselor/leads/${encodeURIComponent(id)}`;

const KIND_LABEL: Record<MilestoneKind, string> = { enrollment: "IT enrolment", application: "Overseas application", visa: "Visa case" };
export const milestoneKind = (kind: MilestoneKind) => KIND_LABEL[kind] ?? kind;
/** Status keys as stored, read aloud ("offer_received" -> "Offer received"). */
export const statusText = (status: string) => (status.charAt(0).toUpperCase() + status.slice(1)).replaceAll("_", " ");

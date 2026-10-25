// ccrm-023 (DEC-SCOPE-245): an application's offer records. The server (services/application_offers.py) is the authority on every rule;
// these mirror its codes and labels for the counselor's Offers panel.

export type ApplicationOfferType = "conditional" | "unconditional" | "pathway" | "other";
export type ApplicationOfferStatus = "active" | "superseded" | "withdrawn_by_university" | "expired";
export type CloseStatus = Extract<ApplicationOfferStatus, "withdrawn_by_university" | "expired">;

export const APPLICATION_OFFER_TYPE_LABELS: Record<ApplicationOfferType, string> = { conditional: "Conditional", unconditional: "Unconditional", pathway: "Pathway", other: "Other" };
export const OFFER_STATUS_LABELS: Record<ApplicationOfferStatus, string> = { active: "Current", superseded: "Superseded", withdrawn_by_university: "Withdrawn by university", expired: "Expired" };
export const CLOSE_STATUSES: CloseStatus[] = ["withdrawn_by_university", "expired"];

export type OfferDocument = { id: string; name: string };
export type ApplicationOffer = {
  id: string;
  offer_type: ApplicationOfferType;
  offer_type_label: string;
  issue_date: string;
  offer_deadline: string | null;
  conditions: string | null;
  currency: string | null;
  tuition_amount: string | null;
  scholarship_amount: string | null;
  deposit_amount: string | null;
  deposit_deadline: string | null;
  document: OfferDocument | null;
  status: ApplicationOfferStatus;
  status_reason: string | null;
  recorded_by: string | null;
  recorded_at: string;
  closed_by: string | null;
  closed_at: string | null;
  decision: OfferDecision;
  decision_label: string;
  decision_date: string | null;
  decided_by: string | null;
  condition_items?: OfferCondition[];
  conditions_summary?: ConditionsSummary;
};
export type OffersPayload = { offers: ApplicationOffer[]; offer_letters: OfferDocument[]; evidence_documents?: OfferDocument[]; agency?: boolean };

// ccrm-024 (DEC-SCOPE-260): an offer's conditions. Met needs evidence (C2); waived and failed need a note (C5); the agent owns one only
// on an agency application (C6). The server checks each rule again.
export type ConditionOwner = "student" | "counselor" | "agent";
export type ConditionStatus = "open" | "met" | "waived" | "failed";
export const CONDITION_OWNER_LABELS: Record<ConditionOwner, string> = { student: "Student", counselor: "Counselor", agent: "Agent" };
export const CONDITION_STATUS_LABELS: Record<ConditionStatus, string> = { open: "Open", met: "Met", waived: "Waived", failed: "Failed" };
export type OfferCondition = {
  id: string;
  description: string;
  owner: ConditionOwner;
  owner_label: string;
  due_date: string | null;
  status: ConditionStatus;
  status_label: string;
  evidence: OfferDocument | null;
  note: string | null;
  status_changed_at: string | null;
};
export type ConditionsSummary = { total: number; satisfied: number; open: number; failed: number; all_satisfied: boolean };

// ccrm-025 (DEC-SCOPE-255): the student's decision on the current offer, and the counselor's manual deposit record (D2).
export type OfferDecision = "considering" | "accepted" | "declined" | "expired";
export type OtherAccepted = { id: string; application_code: string; university: string };
export type DepositStatus = "not_required" | "pending" | "paid_to_university" | "paid_via_edusphere";
export const DEPOSIT_STATUS_LABELS: Record<DepositStatus, string> = {
  not_required: "Not required",
  pending: "Pending",
  paid_to_university: "Paid directly to the university",
  paid_via_edusphere: "Paid via EduSphere",
};
export type DepositRecord = {
  id: string;
  required: boolean;
  amount: string | null;
  currency: string | null;
  due_date: string | null;
  payment_status: DepositStatus;
  payment_status_label: string;
  paid_on: string | null;
  receipt: OfferDocument | null;
  updated_by: string | null;
  updated_at: string;
};
export type AgencyDeposit = { status: string; amount: string | null; currency: string; due_date: string | null };
export type DepositPayload = {
  record: DepositRecord | null;
  agency_deposit: AgencyDeposit | null;
  prefill: { amount: string; currency: string | null; due_date: string | null } | null;
  receipts: OfferDocument[];
};

/** D1: the success message names the student's other accepted offers -- a warning, never a block. */
export function acceptedMessage(others: OtherAccepted[]): string {
  if (others.length === 0) return "Offer accepted.";
  const list = others.map((o) => `${o.application_code} (${o.university})`).join(", ");
  return `Offer accepted. Note: this student has also accepted ${others.length === 1 ? "an offer" : "offers"} on ${list}.`;
}

const APPLICATION_URL = (id: string) => `/api/v1/workflows/overseas/applications/${id}`;
export const offersUrl = (id: string) => `${APPLICATION_URL(id)}/offers`;
export const offerLettersUrl = (id: string) => `${APPLICATION_URL(id)}/offer-letters`;
export const withdrawUrl = (id: string, offerId: string) => `${offersUrl(id)}/${offerId}/withdraw`;
export const decisionUrl = (id: string, offerId: string) => `${offersUrl(id)}/${offerId}/decision`;
export const depositUrl = (id: string) => `${APPLICATION_URL(id)}/deposit`;
export const depositReceiptsUrl = (id: string) => `${APPLICATION_URL(id)}/deposit-receipts`;
export const documentDownloadUrl = (documentId: string) => `/api/v1/workflows/overseas/documents/${documentId}/download`;
export const conditionsUrl = (id: string, offerId: string) => `${offersUrl(id)}/${offerId}/conditions`;
export const conditionUrl = (id: string, offerId: string, conditionId: string) => `${conditionsUrl(id, offerId)}/${conditionId}`;
export const conditionEvidenceUrl = (id: string) => `${APPLICATION_URL(id)}/condition-evidence`;

/** C2/C5: the message for a condition that cannot be saved as it stands, or null. */
export function conditionProblem(status: ConditionStatus, hasEvidence: boolean, note: string): string | null {
  if (status === "met" && !hasEvidence) return "Attach the evidence before marking the condition met.";
  if ((status === "waived" || status === "failed") && !note.trim()) return "Give a note when a condition is waived or failed.";
  return null;
}

export function money(currency: string | null, amount: string | null): string | null {
  return amount === null ? null : `${currency ?? ""} ${Number(amount).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`.trim();
}

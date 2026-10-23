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
};
export type OffersPayload = { offers: ApplicationOffer[]; offer_letters: OfferDocument[] };

const APPLICATION_URL = (id: string) => `/api/v1/workflows/overseas/applications/${id}`;
export const offersUrl = (id: string) => `${APPLICATION_URL(id)}/offers`;
export const offerLettersUrl = (id: string) => `${APPLICATION_URL(id)}/offer-letters`;
export const withdrawUrl = (id: string, offerId: string) => `${offersUrl(id)}/${offerId}/withdraw`;
export const documentDownloadUrl = (documentId: string) => `/api/v1/workflows/overseas/documents/${documentId}/download`;

export function money(currency: string | null, amount: string | null): string | null {
  return amount === null ? null : `${currency ?? ""} ${Number(amount).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`.trim();
}

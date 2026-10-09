// upc-014 (DEC-SCOPE-140): §13 MoU / agreement management -- types, words, URLs and the menu list's query helpers. The API decides every
// permission and move (`permissions`, `moves`); nothing here filters for security.
import type { LookupPage } from "@/lib/lookups";
import type { ManagerRef } from "@/lib/telecaller";
import { UNIVERSITIES_URL } from "@/lib/universities";

export const AGREEMENT_TYPES: Record<string, string> = { mou: "MoU", partnership_agreement: "Partnership agreement", commission_agreement: "Commission agreement" };
export const EXCLUSIVITY: Record<string, string> = { exclusive: "Exclusive", non_exclusive: "Non-exclusive" };
// §13's flow in source order; Expiring and Expired are derived from the expiry date (AG4).
export const AGREEMENT_STATUSES: Record<string, string> = {
  draft: "Draft", sent: "Sent", under_review: "Under Review", negotiation: "Negotiation", approved: "Approved", signed: "Signed",
  active: "Active", expiring: "Expiring", expired: "Expired", renewed: "Renewed",
};
// AG13: who reads agreements (the API answers 403 for anyone else, so the university page doesn't ask).
export const AGREEMENT_READERS = new Set(["partnership_manager", "partnership_head", "super_admin"]);

export type AgreementRef = { id: string; mou_number: string; status: string; effective_status: string };
export type AgreementEvent = { kind: string; from_status: string | null; to_status: string; note: string | null; changed: string[]; actor: ManagerRef; created_at: string };
export type Agreement = {
  id: string; mou_number: string; university: { id: string; name: string; university_code: string }; agreement_type: string; type_label: string;
  status: string; effective_status: string; status_label: string; days_to_expiry: number; start_date: string; expiry_date: string;
  renewal_date: string | null; commercial_terms: string | null; exclusivity: string; territory: string | null; recruitment_rights: string | null;
  all_courses: boolean; courses: { id: string; title: string; level: string }[]; countries: { id: string; name: string }[];
  payment_terms: string | null; marketing_rights: string | null;
  document: { id: string; title: string; kind: string; current_version: number } | null;
  edusphere_signatory: ManagerRef | null; edusphere_signed_on: string | null; university_signatory_name: string | null; university_signed_on: string | null;
  previous: AgreementRef | null; renewed_by: AgreementRef | null; created_by: ManagerRef; created_at: string; updated_at: string;
  permissions: { can_edit_terms: boolean; can_edit_signing: boolean; can_renew: boolean };
  moves: { to_status: string; label: string }[];
  events?: AgreementEvent[];
};
export type AgreementOptions = {
  courses: { id: string; title: string; level: string }[];
  documents: { id: string; kind: string; title: string; current_version: number }[];
};

export const AGREEMENTS_URL = "/api/v1/partnership/agreements";
export const AGREEMENTS_PATH = "/partnership/agreements";
export const agreementsUrl = (universityId: string) => `${UNIVERSITIES_URL}/${universityId}/agreements`;
export const agreementOptionsUrl = (universityId: string) => `${UNIVERSITIES_URL}/${universityId}/agreement-options`;
export const agreementUrl = (id: string, tail = "") => `${AGREEMENTS_URL}/${id}${tail}`;

/** AG7: who may sign for EduSphere (active partnership staff and super admins), searched by name or email. */
export async function signatorySearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: "20" });
  if (q) query.set("q", q);
  const response = await fetch(`/api/v1/partnership/agreement-signatories?${query}`, { signal });
  if (!response.ok) throw new Error(`Signatory search failed (${response.status})`);
  return (await response.json()) as LookupPage;
}

export const typeLabel = (type: string) => AGREEMENT_TYPES[type] ?? type;
export const statusLabel = (status: string) => AGREEMENT_STATUSES[status] ?? status;

/** A calendar date ("2026-10-09") as "09 Oct 2026" -- no time zone involved. */
export function dateText(value: string | null): string {
  if (!value) return "—";
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

/** "Expires in 30 days", "Expires today", "Expired 3 days ago" -- for an agreement in force (signed / active). */
export function expiryText(a: Pick<Agreement, "status" | "days_to_expiry">): string | null {
  if (a.status !== "signed" && a.status !== "active") return null;
  const d = a.days_to_expiry;
  if (d === 0) return "Expires today";
  if (d > 0) return `Expires in ${d} day${d === 1 ? "" : "s"}`;
  return `Expired ${-d} day${d === -1 ? "" : "s"} ago`;
}

// The menu page's filters travel in the URL; only these keys are passed on to the API.
export const AGREEMENT_FILTER_KEYS = ["status", "agreement_type", "q"] as const;
export type AgreementFilters = Partial<Record<(typeof AGREEMENT_FILTER_KEYS)[number] | "offset", string>>;

function filterParams(filters: AgreementFilters): URLSearchParams {
  const query = new URLSearchParams();
  for (const key of AGREEMENT_FILTER_KEYS) {
    const value = filters[key]?.trim();
    if (value) query.set(key, value);
  }
  return query;
}

export function agreementListQuery(filters: AgreementFilters, limit: number, offset: number): string {
  const query = filterParams(filters);
  query.set("limit", String(limit));
  query.set("offset", String(offset));
  return query.toString();
}

export function agreementPageHref(filters: AgreementFilters, offset: number): string {
  const query = filterParams(filters);
  if (offset > 0) query.set("offset", String(offset));
  const text = query.toString();
  return text ? `${AGREEMENTS_PATH}?${text}` : AGREEMENTS_PATH;
}

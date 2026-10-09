// upc-016 (DEC-SCOPE-144): §15 commercial / commission terms -- RESTRICTED (U2). Types, words, URLs and the menu list's query helpers.
// The API is the gate: it answers 403 to every non-commission role and leaves `commission_terms` out of their agreements. Nothing here
// filters for security.
import type { ManagerRef } from "@/lib/telecaller";
import { AGREEMENTS_URL } from "@/lib/universityAgreements";

export { CURRENCIES } from "@/lib/agentStudents"; // CM3: the project's currency list (models.COMMISSION_CURRENCIES)
export const TRIGGERS: Record<string, string> = { enrolment: "Student enrolment", visa_and_enrolment: "Visa approval + enrolment", tuition_paid: "Tuition paid" }; // CM1

export type CommissionTerm = {
  id: string; agreement_id: string; commission_percent: string | null; fixed_amount: string | null; currency: string; trigger: string;
  trigger_label: string; conditions: string | null; courses: { id: string; title: string; level: string }[]; countries: { id: string; name: string }[];
  payment_timeline: string | null; payment_terms: string | null; created_by: ManagerRef; updated_by: ManagerRef; created_at: string; updated_at: string;
  permissions: { can_edit: boolean };
};
export type CommissionTermRow = CommissionTerm & {
  agreement: { id: string; mou_number: string; agreement_type: string; type_label: string; status: string; effective_status: string; status_label: string };
  university: { id: string; name: string; university_code: string };
};

export const COMMISSION_TERMS_URL = "/api/v1/partnership/commission-terms";
export const COMMISSION_TERMS_PATH = "/partnership/commercial-terms";
export const termsUrl = (agreementId: string, termId?: string) => `${AGREEMENTS_URL}/${agreementId}/commission-terms${termId ? `/${termId}` : ""}`;

/** "15%" / "12.5%" or "GBP 1,500" / "GBP 1,500.50" -- the one rate a term carries (CM2). */
export function rateText(t: Pick<CommissionTerm, "commission_percent" | "fixed_amount" | "currency">): string {
  if (t.commission_percent !== null) return `${Number(t.commission_percent)}%`;
  const n = Number(t.fixed_amount ?? 0);
  const digits = Number.isInteger(n) ? 0 : 2;
  return `${t.currency} ${n.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

/** Who the term applies to: "All programmes · All countries" or the named ones. */
export function scopeText(t: Pick<CommissionTerm, "courses" | "countries">): string {
  const programmes = t.courses.length ? t.courses.map((c) => c.title).join(", ") : "All programmes";
  const countries = t.countries.length ? t.countries.map((c) => c.name).join(", ") : "All countries";
  return `${programmes} · ${countries}`;
}

// The menu page's filters travel in the URL; only these keys are passed on to the API.
export const TERM_FILTER_KEYS = ["trigger", "currency", "q"] as const;
export type TermFilters = Partial<Record<(typeof TERM_FILTER_KEYS)[number] | "offset", string>>;

function filterParams(filters: TermFilters): URLSearchParams {
  const query = new URLSearchParams();
  for (const key of TERM_FILTER_KEYS) {
    const value = filters[key]?.trim();
    if (value) query.set(key, value);
  }
  return query;
}

export function termListQuery(filters: TermFilters, limit: number, offset: number): string {
  const query = filterParams(filters);
  query.set("limit", String(limit));
  query.set("offset", String(offset));
  return query.toString();
}

export function termPageHref(filters: TermFilters, offset: number): string {
  const query = filterParams(filters);
  if (offset > 0) query.set("offset", String(offset));
  const text = query.toString();
  return text ? `${COMMISSION_TERMS_PATH}?${text}` : COMMISSION_TERMS_PATH;
}

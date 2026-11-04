// rec-009 (DEC-SCOPE-122): the candidate master -- types, endpoints, labels and the form <-> body mapping shared by the list, the create
// form and the detail. Labels are display only; the API decides who may read or write and every rule (Q-07 duplicates, Q-08 statuses).
import type { PersonRef } from "@/lib/telecallerLeads";

export type CandidateStatus = "available" | "interviewing" | "placed" | "not_looking" | "do_not_contact";
export type SourceRef = { id: string; name: string; active: boolean };
export type CandidateItem = {
  id: string; candidate_code: string; name: string; location: string | null; experience_months: number | null; preferred_role: string | null;
  source: SourceRef; source_detail: string | null; status: CandidateStatus; archived: boolean; created_at: string;
};
export type CandidateResume = {
  version: number; file_name: string | null; content_type: string; size_bytes: number; uploaded_by: PersonRef | null; created_at: string;
  preview_status?: "pending" | "ready" | "failed" | null; // hrc-015: a DOC/DOCX's PDF rendition
};
// hrc-001 (DEC-SCOPE-371 H2): salary is left out (not null) for a caller without this grant, who may not send it either.
export const COMPENSATION_VIEW = "candidates.compensation.view";
// hrc-011 (DEC-SCOPE-375): each amount keeps its currency and pay period beside the normalised annual INR the API works out.
export type SalaryPeriod = "year" | "month";
export const AMOUNTS = [
  { key: "current", label: "Current salary" }, { key: "expected", label: "Expected salary" }, { key: "minimum", label: "Minimum acceptable salary" },
] as const;
type Amount = (typeof AMOUNTS)[number]["key"];
type Package = { [K in Amount as `${K}_salary` | `${K}_annual_inr`]?: string | null } & { [K in Amount as `${K}_salary_currency`]?: string | null }
  & { [K in Amount as `${K}_salary_period`]?: SalaryPeriod | null } & { salary_negotiable?: boolean | null };
export const PERIOD_LABEL: Record<SalaryPeriod, string> = { year: "per year", month: "per month" };
export const NEGOTIABLE = [{ key: "", label: "Not provided" }, { key: "yes", label: "Yes" }, { key: "no", label: "No" }] as const;
type PackageForm = { [K in Amount as `${K}_salary` | `${K}_salary_currency` | `${K}_salary_period`]: string } & { salary_negotiable: string };
const SALARY_KEYS = new Set<string>([...AMOUNTS.flatMap(({ key }) => [`${key}_salary`, `${key}_salary_currency`, `${key}_salary_period`]), "salary_negotiable"]);
/** The stale-record notice's labels for the compensation keys. */
export const COMPENSATION_LABELS: Record<string, string> = {
  ...Object.fromEntries(AMOUNTS.flatMap(({ key, label }) => [[`${key}_salary`, label], [`${key}_salary_currency`, `${label} currency`], [`${key}_salary_period`, `${label} pay period`]])),
  salary_negotiable: "Negotiable",
};
export type CandidateDetail = CandidateItem & Package & {
  mobile: string | null; email: string | null; qualification: string | null; college: string | null; passing_year: number | null;
  current_company: string | null; notice_days: number | null;
  preferred_locations: string[]; linkedin: string | null; archived_at: string | null; created_by: PersonRef | null; updated_by: PersonRef | null;
  updated_at: string; resumes: CandidateResume[]; can_edit: boolean; whatsapp_to?: string | null; // rec-026: the wa.me number
  merged_into?: { id: string; candidate_code: string } | null; // hrc-014: the candidate this one was merged into
};
/** Q-07: one existing candidate of the duplicate panel -- never their mobile or email. */
export type CandidateMatch = { id: string; candidate_code: string; name: string; source_name: string; status: CandidateStatus; archived: boolean; matched_on: ("mobile" | "email")[] };

export const CANDIDATES_URL = "/api/v1/recruiter/candidates";
export const CANDIDATES_PATH = "/recruiter/candidates";
export const DUPLICATE_CHECK_URL = `${CANDIDATES_URL}/duplicate-check`;
export const candidateUrl = (id: string, suffix = "") => `${CANDIDATES_URL}/${encodeURIComponent(id)}${suffix}`;
export const resumeUrl = (id: string, version: number) => candidateUrl(id, `/resume/${version}`);
export const resumeLinkUrl = (id: string, version: number) => candidateUrl(id, `/resume/${version}/link`); // hrc-015 D4
export const RESUME_ACCEPT = ".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document";
export const RESUME_MAX_BYTES = 5 * 1024 * 1024;

export const STATUSES: { key: CandidateStatus; label: string }[] = [
  { key: "available", label: "Available" }, { key: "interviewing", label: "Interviewing" }, { key: "placed", label: "Placed" },
  { key: "not_looking", label: "Not looking" }, { key: "do_not_contact", label: "Do not contact" },
];
export const STATUS_LABEL: Record<string, string> = Object.fromEntries(STATUSES.map((s) => [s.key, s.label]));

type Field = { key: keyof CandidateForm; label: string; type: "text" | "tel" | "email" | "number" | "url"; max?: number; min?: number; numMax?: number; hint?: string };
// EVID-018 §8 in source order (name, mobile and email first; resume and source have their own controls).
export const FIELDS: Field[] = [
  { key: "name", label: "Name", type: "text", max: 160 },
  { key: "mobile", label: "Mobile", type: "tel", max: 40, hint: "10 digits, or + and the country code" },
  { key: "email", label: "Email", type: "email", max: 255 },
  { key: "location", label: "Location", type: "text", max: 120 },
  { key: "qualification", label: "Qualification", type: "text", max: 120 },
  { key: "college", label: "College", type: "text", max: 200 },
  { key: "passing_year", label: "Passing year", type: "number", min: 1950, numMax: 2100 },
  { key: "experience_months", label: "Total experience (months)", type: "number", min: 0, numMax: 600, hint: "e.g. 30 for 2 years 6 months; 0 for a fresher" },
  { key: "current_company", label: "Current company", type: "text", max: 200 },
  { key: "notice_days", label: "Notice period (days)", type: "number", min: 0, numMax: 365 },
  { key: "preferred_locations", label: "Preferred locations", type: "text", max: 900, hint: "Separate places with commas (up to 10)" },
  { key: "preferred_role", label: "Preferred role", type: "text", max: 120 },
  { key: "linkedin", label: "LinkedIn", type: "url", max: 300, hint: "https://www.linkedin.com/in/…" },
];

export type CandidateForm = PackageForm & {
  name: string; mobile: string; email: string; location: string; qualification: string; college: string; passing_year: string;
  experience_months: string; current_company: string; notice_days: string;
  preferred_locations: string; preferred_role: string; linkedin: string; source_id: string; source_detail: string; status: CandidateStatus;
};
const EMPTY_PACKAGE = {
  ...Object.fromEntries(AMOUNTS.flatMap(({ key }) => [[`${key}_salary`, ""], [`${key}_salary_currency`, "INR"], [`${key}_salary_period`, "year"]])),
  salary_negotiable: "",
} as PackageForm;
export const EMPTY_FORM: CandidateForm = {
  name: "", mobile: "", email: "", location: "", qualification: "", college: "", passing_year: "", experience_months: "", current_company: "",
  ...EMPTY_PACKAGE, notice_days: "", preferred_locations: "", preferred_role: "", linkedin: "", source_id: "",
  source_detail: "", status: "available",
};
const INTEGERS = new Set<keyof CandidateForm>(["passing_year", "experience_months", "notice_days"]);

const places = (text: string) => text.split(",").map((p) => p.trim()).filter(Boolean);

/** hrc-011: a currency or pay period means nothing without its amount (the API clears them then), so it goes with the amount. */
const amountOf = (key: string) => key.replace(/_(currency|period)$/, "");

/** The request body. Create sends only what is filled; edit sends every field, a cleared one as null (PATCH clears it). Salaries stay
 *  strings (the API takes decimals); the whole-number fields become numbers; Negotiable is true / false / null. Without the
 *  compensation grant no compensation key is sent. */
export function candidateBody(form: CandidateForm, mode: "create" | "edit", compensation = true): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const [key, raw] of Object.entries(form) as [keyof CandidateForm, string][]) {
    if (!compensation && SALARY_KEYS.has(key)) continue;
    const text = raw.trim();
    const withoutAmount = SALARY_KEYS.has(key) && key !== "salary_negotiable" && !form[amountOf(key) as keyof CandidateForm].trim();
    const value = key === "preferred_locations" ? places(text) : !text || withoutAmount ? null
      : key === "salary_negotiable" ? text === "yes" : INTEGERS.has(key) ? Number(text) : text;
    const empty = value === null || (Array.isArray(value) && value.length === 0);
    if (mode === "create" && empty) continue;
    body[key] = value;
  }
  return body;
}

/** The form's own required check, so an incomplete form sends nothing. Null when complete. */
export function missingRequired(form: CandidateForm): string | null {
  const contact = !form.mobile.trim() && !form.email.trim();
  const fields = [!form.name.trim() && "name", !form.source_id && "source"].filter(Boolean) as string[];
  // "the name, source and a mobile …", "the name and source", "a mobile …" -- never "the a mobile" (QA-01)
  const items = [...(fields.length ? [`the ${fields.join(contact ? ", " : " and ")}`] : []), ...(contact ? ["a mobile number or an email"] : [])];
  return items.length ? `Enter ${items.join(" and ")}.` : null;
}

export function formFromDetail(c: CandidateDetail): CandidateForm {
  const text = (v: string | number | null | undefined) => (v === null || v === undefined ? "" : String(v));
  return {
    ...EMPTY_FORM,
    ...Object.fromEntries(FIELDS.map(({ key }) => [key, text(c[key as keyof CandidateDetail] as string | number | null)])),
    ...Object.fromEntries(AMOUNTS.flatMap(({ key }) => [
      [`${key}_salary`, text(c[`${key}_salary`])], [`${key}_salary_currency`, c[`${key}_salary_currency`] ?? "INR"], [`${key}_salary_period`, c[`${key}_salary_period`] ?? "year"],
    ])),
    salary_negotiable: c.salary_negotiable === true ? "yes" : c.salary_negotiable === false ? "no" : "",
    preferred_locations: (c.preferred_locations ?? []).join(", "), source_id: c.source.id, source_detail: text(c.source_detail), status: c.status,
  };
}

const inr = (v: string) => `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

/** hrc-011: an amount as entered ("₹50,000 per month", "USD 4,000 per month"), then its annual INR when that reads differently
 *  ("≈ ₹6,00,000 a year"). Null when not provided. */
export function packageText(c: CandidateDetail, amount: Amount): string | null {
  const value = c[`${amount}_salary`];
  if (value === null || value === undefined) return null;
  const currency = c[`${amount}_salary_currency`] ?? "INR";
  const period = c[`${amount}_salary_period`] ?? "year";
  const entered = `${currency === "INR" ? inr(value) : `${currency} ${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`} ${PERIOD_LABEL[period]}`;
  const annual = c[`${amount}_annual_inr`];
  return currency === "INR" && period === "year" || !annual ? entered : `${entered} (≈ ${inr(annual)} a year)`;
}

export function experienceLabel(months: number | null): string {
  if (months === null || months === undefined) return "—";
  if (months === 0) return "Fresher";
  const years = Math.floor(months / 12);
  const rest = months % 12;
  return [years && `${years} yr`, rest && `${rest} mo`].filter(Boolean).join(" ");
}

export const fileSize = (bytes: number) => (bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

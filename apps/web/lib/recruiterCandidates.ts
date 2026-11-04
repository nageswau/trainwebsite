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
// hrc-010 (DEC-SCOPE-382): the §5 profile rows (a sent list replaces the whole set), the enums and the Appendix B completeness.
export type EducationRow = { degree: string | null; specialisation: string | null; institution: string | null; year: number | null; grade: string | null };
export type EmploymentRow = { employer: string; designation: string | null; industry: string | null; employment_type: string | null; start_date: string; end_date: string | null };
export type CertificationRow = { name: string; issuer: string | null; issued_on: string | null; expires_on: string | null; credential_id: string | null };
export type Completeness = { percent: number; items: { key: string; label: string; weight: number; met: boolean }[] };
export const WORK_MODES = [{ key: "onsite", label: "On-site" }, { key: "hybrid", label: "Hybrid" }, { key: "remote", label: "Remote" }];
export const EMPLOYMENT_TYPES = [
  { key: "full_time", label: "Full time" }, { key: "part_time", label: "Part time" }, { key: "contract", label: "Contract" },
  { key: "internship", label: "Internship" }, { key: "temporary", label: "Temporary" },
];
export const SHIFTS = [{ key: "day", label: "Day" }, { key: "night", label: "Night" }, { key: "rotational", label: "Rotational" }, { key: "flexible", label: "Flexible" }];
export const CONTACT_METHODS = [{ key: "phone", label: "Phone call" }, { key: "whatsapp", label: "WhatsApp" }, { key: "email", label: "Email" }];
export const CHOICES = { work_modes: WORK_MODES, employment_types: EMPLOYMENT_TYPES, shifts: SHIFTS } as const;
export const labelOf = (options: readonly { key: string; label: string }[], key: string | null | undefined) => options.find((o) => o.key === key)?.label ?? key ?? "";
type RowColumn = { key: string; label: string; type: "text" | "number" | "date" | "select"; max?: number; min?: number; numMax?: number; required?: boolean; options?: { key: string; label: string }[]; hint?: string };
export type RowKind = "education" | "employment" | "certifications";
export const ROW_KINDS: Record<RowKind, { legend: string; noun: string; columns: RowColumn[] }> = {
  education: { legend: "Education", noun: "education", columns: [
    { key: "degree", label: "Degree", type: "text", max: 120, hint: "e.g. B.Tech" }, { key: "specialisation", label: "Specialisation", type: "text", max: 120 },
    { key: "institution", label: "Institution", type: "text", max: 200 }, { key: "year", label: "Year", type: "number", min: 1950, numMax: 2100 },
    { key: "grade", label: "Marks / CGPA", type: "text", max: 20, hint: "Optional, e.g. 8.2 CGPA or 78%" },
  ] },
  employment: { legend: "Employment history", noun: "employment", columns: [
    { key: "employer", label: "Employer", type: "text", max: 200, required: true }, { key: "designation", label: "Designation", type: "text", max: 120 },
    { key: "industry", label: "Industry", type: "text", max: 120 }, { key: "employment_type", label: "Employment type", type: "select", options: EMPLOYMENT_TYPES },
    { key: "start_date", label: "Start date", type: "date", required: true }, { key: "end_date", label: "End date", type: "date", hint: "Leave empty for the current job" },
  ] },
  certifications: { legend: "Certifications", noun: "certification", columns: [
    { key: "name", label: "Certification", type: "text", max: 200, required: true }, { key: "issuer", label: "Issuer", type: "text", max: 200 },
    { key: "issued_on", label: "Issued on", type: "date" }, { key: "expires_on", label: "Expires on", type: "date" },
    { key: "credential_id", label: "Credential ID", type: "text", max: 100 },
  ] },
};
export type FormRow = Record<string, string>;
const ROW_KEYS = Object.keys(ROW_KINDS) as RowKind[];
export const parseRows = (text: string): FormRow[] => { try { const rows = JSON.parse(text || "[]"); return Array.isArray(rows) ? rows : []; } catch { return []; } };
export const emptyRow = (kind: RowKind): FormRow => Object.fromEntries(ROW_KINDS[kind].columns.map((c) => [c.key, ""]));
const filledRows = (text: string) => parseRows(text).filter((row) => Object.values(row).some((v) => String(v ?? "").trim()));
/** One stored row as one line, for the detail and the stale-record notice ("B.Tech · Computer Science · JNTU · 2018"). */
export function rowText(kind: RowKind, row: Record<string, unknown>): string {
  return ROW_KINDS[kind].columns.map((c) => (c.options ? labelOf(c.options, row[c.key] as string) : row[c.key])).filter((v) => v !== null && v !== undefined && v !== "").join(" · ");
}

/** QA-02: with no education rows, the legacy single fields (set by rec-012's resume apply or an old client) read as row 1. */
export function educationRows(c: CandidateDetail): EducationRow[] {
  if (c.education?.length) return c.education;
  return c.qualification || c.college || c.passing_year
    ? [{ degree: c.qualification, specialisation: null, institution: c.college, year: c.passing_year, grade: null }] : [];
}

export type CandidateDetail = CandidateItem & Package & {
  mobile: string | null; email: string | null; qualification: string | null; college: string | null; passing_year: number | null;
  current_company: string | null; notice_days: number | null;
  preferred_locations: string[]; linkedin: string | null; archived_at: string | null; created_by: PersonRef | null; updated_by: PersonRef | null;
  updated_at: string; resumes: CandidateResume[]; can_edit: boolean; whatsapp_to?: string | null; // rec-026: the wa.me number
  merged_into?: { id: string; candidate_code: string } | null; // hrc-014: the candidate this one was merged into
  // hrc-010 (optional: an older API answer has none of these)
  country?: string | null; state?: string | null; city?: string | null; preferred_contact?: string | null; email_verified_at?: string | null;
  relevant_experience_months?: number | null; tools?: string[]; languages?: string[]; preferred_roles?: string[]; work_modes?: string[];
  employment_types?: string[]; shifts?: string[]; available_from?: string | null; willing_to_relocate?: boolean | null;
  education?: EducationRow[]; employment?: EmploymentRow[]; certifications?: CertificationRow[]; is_fresher?: boolean | null; completeness?: Completeness | null;
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

export type FieldGroup = "basic" | "location" | "experience" | "skills" | "preferences";
type Field = {
  key: keyof CandidateForm; label: string; type: "text" | "tel" | "email" | "number" | "url" | "date"; max?: number; min?: number; numMax?: number; hint?: string;
  group: FieldGroup; when?: (form: CandidateForm) => boolean; // shown (and sent) only while `when` holds
};
const hasRows = (form: CandidateForm, kind: RowKind) => filledRows(form[kind]).length > 0;
const hasPlace = (form: CandidateForm) => [form.city, form.state, form.country].some((v) => v.trim());
// EVID-018 §8 in source order (name, mobile and email first; resume and source have their own controls). hrc-010: grouped by §5 section;
// qualification, college and passing year come from the education rows, so they have no input of their own.
export const FIELDS: Field[] = [
  { key: "name", label: "Name", type: "text", max: 160, group: "basic" },
  { key: "mobile", label: "Mobile", type: "tel", max: 40, hint: "10 digits, or + and the country code", group: "basic" },
  { key: "email", label: "Email", type: "email", max: 255, group: "basic" },
  { key: "notice_days", label: "Notice period (days)", type: "number", min: 0, numMax: 365, group: "basic" },
  { key: "linkedin", label: "LinkedIn", type: "url", max: 300, hint: "https://www.linkedin.com/in/…", group: "basic" },
  { key: "city", label: "City", type: "text", max: 80, group: "location" },
  { key: "state", label: "State", type: "text", max: 80, group: "location" },
  { key: "country", label: "Country", type: "text", max: 80, group: "location" },
  { key: "location", label: "Location", type: "text", max: 120, group: "location", when: (f) => !hasPlace(f), hint: "Replaced by the city, state and country once entered" },
  { key: "experience_months", label: "Total experience (months)", type: "number", min: 0, numMax: 600, hint: "e.g. 30 for 2 years 6 months; 0 for a fresher", group: "experience", when: (f) => !hasRows(f, "employment") },
  { key: "current_company", label: "Current company", type: "text", max: 200, group: "experience", when: (f) => !hasRows(f, "employment") },
  { key: "relevant_experience_months", label: "Relevant experience (months)", type: "number", min: 0, numMax: 600, hint: "For the preferred role", group: "experience" },
  { key: "tools", label: "Tools", type: "text", max: 1300, hint: "Separate with commas, e.g. Git, Jira (up to 20)", group: "skills" },
  { key: "languages", label: "Languages", type: "text", max: 1300, hint: "Separate with commas, e.g. English, Telugu (up to 20)", group: "skills" },
  { key: "preferred_roles", label: "Preferred roles", type: "text", max: 650, hint: "Separate with commas; the first is the main role (up to 5)", group: "preferences" },
  { key: "preferred_locations", label: "Preferred locations", type: "text", max: 900, hint: "Separate places with commas (up to 10)", group: "preferences" },
  { key: "available_from", label: "Available from", type: "date", group: "preferences" },
];
export const shownFields = (form: CandidateForm, group: FieldGroup) => FIELDS.filter((f) => f.group === group && (!f.when || f.when(form)));

// hrc-010: the rows are JSON text and the enum sets comma-joined keys, so the hrc-003 stale guard compares every value as a string.
type ProfileForm = Record<RowKind | keyof typeof CHOICES, string> & {
  country: string; state: string; city: string; preferred_contact: string; relevant_experience_months: string; tools: string; languages: string;
  preferred_roles: string; available_from: string; willing_to_relocate: string;
};
export type CandidateForm = PackageForm & ProfileForm & {
  name: string; mobile: string; email: string; location: string; experience_months: string; current_company: string; notice_days: string;
  preferred_locations: string; linkedin: string; source_id: string; source_detail: string; status: CandidateStatus;
};
const EMPTY_PACKAGE = {
  ...Object.fromEntries(AMOUNTS.flatMap(({ key }) => [[`${key}_salary`, ""], [`${key}_salary_currency`, "INR"], [`${key}_salary_period`, "year"]])),
  salary_negotiable: "",
} as PackageForm;
const EMPTY_PROFILE: ProfileForm = {
  country: "", state: "", city: "", preferred_contact: "", relevant_experience_months: "", tools: "", languages: "", preferred_roles: "",
  work_modes: "", employment_types: "", shifts: "", available_from: "", willing_to_relocate: "", education: "[]", employment: "[]", certifications: "[]",
};
export const EMPTY_FORM: CandidateForm = {
  name: "", mobile: "", email: "", location: "", experience_months: "", current_company: "",
  ...EMPTY_PACKAGE, ...EMPTY_PROFILE, notice_days: "", preferred_locations: "", linkedin: "", source_id: "",
  source_detail: "", status: "available",
};
const INTEGERS = new Set<keyof CandidateForm>(["experience_months", "notice_days", "relevant_experience_months"]);
const LISTS = new Set<keyof CandidateForm>(["preferred_locations", "tools", "languages", "preferred_roles"]);
const YES_NO = new Set<keyof CandidateForm>(["salary_negotiable", "willing_to_relocate"]);

const places = (text: string) => text.split(",").map((p) => p.trim()).filter(Boolean);
const rowBody = (kind: RowKind, text: string) => filledRows(text).map((row) => Object.fromEntries(ROW_KINDS[kind].columns.map(({ key, type }) => {
  const value = String(row[key] ?? "").trim();
  return [key, !value ? null : type === "number" ? Number(value) : value];
})));

/** hrc-011: a currency or pay period means nothing without its amount (the API clears them then), so it goes with the amount. */
const amountOf = (key: string) => key.replace(/_(currency|period)$/, "");

/** The request body. Create sends only what is filled; edit sends every field, a cleared one as null (PATCH clears it). Salaries stay
 *  strings (the API takes decimals); the whole-number fields become numbers; Negotiable is true / false / null. Without the
 *  compensation grant no compensation key is sent. */
export function candidateBody(form: CandidateForm, mode: "create" | "edit", compensation = true): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  const hidden = new Set(FIELDS.filter((f) => f.when && !f.when(form)).map((f) => f.key)); // hrc-010: their rows decide them
  for (const [key, raw] of Object.entries(form) as [keyof CandidateForm, string][]) {
    if ((!compensation && SALARY_KEYS.has(key)) || hidden.has(key)) continue;
    const text = raw.trim();
    const withoutAmount = SALARY_KEYS.has(key) && key !== "salary_negotiable" && !form[amountOf(key) as keyof CandidateForm].trim();
    const value = LISTS.has(key) ? places(text) : key in ROW_KINDS ? rowBody(key as RowKind, raw) : key in CHOICES ? text.split(",").filter(Boolean)
      : !text || withoutAmount ? null : YES_NO.has(key) ? text === "yes" : INTEGERS.has(key) ? Number(text) : text;
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
    // hrc-010
    preferred_contact: text(c.preferred_contact), tools: (c.tools ?? []).join(", "), languages: (c.languages ?? []).join(", "),
    preferred_roles: (c.preferred_roles?.length ? c.preferred_roles : c.preferred_role ? [c.preferred_role] : []).join(", "),
    ...Object.fromEntries(Object.keys(CHOICES).map((k) => [k, ((c[k as keyof typeof CHOICES] as string[] | undefined) ?? []).join(",")])),
    willing_to_relocate: c.willing_to_relocate === true ? "yes" : c.willing_to_relocate === false ? "no" : "",
    ...Object.fromEntries(ROW_KEYS.map((kind) => [kind, JSON.stringify(((kind === "education" ? educationRows(c) : c[kind] ?? []) as Record<string, unknown>[]).map((row) =>
      Object.fromEntries(ROW_KINDS[kind].columns.map(({ key }) => [key, text(row[key] as string | number | null)]))))])),
  };
}

/** hrc-010: the stale-record notice shows a row set as its lines and an enum set as its labels, not the form's JSON. */
export function displayValue(key: string, value: string): string {
  if (key in ROW_KINDS) return filledRows(value).map((row) => rowText(key as RowKind, row)).join("; ");
  if (key in CHOICES) return value.split(",").filter(Boolean).map((k) => labelOf(CHOICES[key as keyof typeof CHOICES], k)).join(", ");
  return value;
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

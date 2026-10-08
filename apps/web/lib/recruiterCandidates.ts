// rec-009 (DEC-SCOPE-122): the candidate master -- types, endpoints, labels and the form <-> body mapping shared by the list, the create
// form and the detail. Labels are display only; the API decides who may read or write and every rule (Q-07 duplicates, Q-08 statuses).
import type { PersonRef } from "@/lib/telecallerLeads";

export type CandidateStatus = "available" | "interviewing" | "placed" | "not_looking" | "do_not_contact";
export type SourceRef = { id: string; name: string; active: boolean };
export type CandidateItem = {
  id: string; candidate_code: string; name: string; location: string | null; experience_months: number | null; preferred_role: string | null;
  source: SourceRef; source_detail: string | null; status: CandidateStatus; archived: boolean; created_at: string;
};
export type CandidateResume = { version: number; file_name: string | null; content_type: string; size_bytes: number; uploaded_by: PersonRef | null; created_at: string };
export type CandidateDetail = CandidateItem & {
  mobile: string | null; email: string | null; qualification: string | null; college: string | null; passing_year: number | null;
  current_company: string | null; current_salary: string | null; expected_salary: string | null; notice_days: number | null;
  preferred_locations: string[]; linkedin: string | null; archived_at: string | null; created_by: PersonRef | null; updated_by: PersonRef | null;
  updated_at: string; resumes: CandidateResume[]; can_edit: boolean; whatsapp_to?: string | null; // rec-026: the wa.me number
};
/** Q-07: one existing candidate of the duplicate panel -- never their mobile or email. */
export type CandidateMatch = { id: string; candidate_code: string; name: string; source_name: string; status: CandidateStatus; archived: boolean; matched_on: ("mobile" | "email")[] };

export const CANDIDATES_URL = "/api/v1/recruiter/candidates";
export const CANDIDATES_PATH = "/recruiter/candidates";
export const DUPLICATE_CHECK_URL = `${CANDIDATES_URL}/duplicate-check`;
export const candidateUrl = (id: string, suffix = "") => `${CANDIDATES_URL}/${encodeURIComponent(id)}${suffix}`;
export const resumeUrl = (id: string, version: number) => candidateUrl(id, `/resume/${version}`);
export const RESUME_ACCEPT = ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";
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
  { key: "current_salary", label: "Current salary (per year)", type: "number", min: 0 },
  { key: "expected_salary", label: "Expected salary (per year)", type: "number", min: 0 },
  { key: "notice_days", label: "Notice period (days)", type: "number", min: 0, numMax: 365 },
  { key: "preferred_locations", label: "Preferred locations", type: "text", max: 900, hint: "Separate places with commas (up to 10)" },
  { key: "preferred_role", label: "Preferred role", type: "text", max: 120 },
  { key: "linkedin", label: "LinkedIn", type: "url", max: 300, hint: "https://www.linkedin.com/in/…" },
];

export type CandidateForm = {
  name: string; mobile: string; email: string; location: string; qualification: string; college: string; passing_year: string;
  experience_months: string; current_company: string; current_salary: string; expected_salary: string; notice_days: string;
  preferred_locations: string; preferred_role: string; linkedin: string; source_id: string; source_detail: string; status: CandidateStatus;
};
export const EMPTY_FORM: CandidateForm = {
  name: "", mobile: "", email: "", location: "", qualification: "", college: "", passing_year: "", experience_months: "", current_company: "",
  current_salary: "", expected_salary: "", notice_days: "", preferred_locations: "", preferred_role: "", linkedin: "", source_id: "",
  source_detail: "", status: "available",
};
const INTEGERS = new Set<keyof CandidateForm>(["passing_year", "experience_months", "notice_days"]);

const places = (text: string) => text.split(",").map((p) => p.trim()).filter(Boolean);

/** The request body. Create sends only what is filled; edit sends every field, a cleared one as null (PATCH clears it). Salaries stay
 *  strings (the API takes decimals); the whole-number fields become numbers. */
export function candidateBody(form: CandidateForm, mode: "create" | "edit"): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const [key, raw] of Object.entries(form) as [keyof CandidateForm, string][]) {
    const text = raw.trim();
    const value = key === "preferred_locations" ? places(text) : !text ? null : INTEGERS.has(key) ? Number(text) : text;
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
    preferred_locations: (c.preferred_locations ?? []).join(", "), source_id: c.source.id, source_detail: text(c.source_detail), status: c.status,
  };
}

export function experienceLabel(months: number | null): string {
  if (months === null || months === undefined) return "—";
  if (months === 0) return "Fresher";
  const years = Math.floor(months / 12);
  const rest = months % 12;
  return [years && `${years} yr`, rest && `${rest} mo`].filter(Boolean).join(" ");
}

export const fileSize = (bytes: number) => (bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

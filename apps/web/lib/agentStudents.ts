// AGN-004 (DEC-SCOPE-042): the shape and helpers of an agency student (with or without a login), shared by the list, the detail
// panel and the form so they read one definition. Validation mirrors the server's schemas; the server remains the authority.

export const RECORDS_URL = "/api/v1/workflows/overseas/agent/crm/students";

export type Assignee = { id: string; code: string; full_name: string; status: string };
export type AgentStudentItem = {
  id: string;
  has_login: boolean;
  full_name: string;
  email: string | null;
  phone: string | null;
  preferred_country: string | null;
  preferred_intake: string | null;
  status: "active" | "archived";
  assigned_to: Assignee | null;
  created_at: string;
};
export type AgentStudentDetail = AgentStudentItem & {
  date_of_birth: string | null;
  highest_qualification: string | null;
  institution: string | null;
  graduation_year: number | null;
  preferred_course: string | null;
  notes: string | null;
  created_by: string | null;
  archived_at: string | null;
  archived_by: string | null;
  updated_at: string;
};
export type DuplicateMatch = { id: string; full_name: string; has_login: boolean; status: string; matched_on: string[] };
export type DuplicateDetail = { message: string; matches: DuplicateMatch[]; hidden_matches: number };

export const FIELD_KEYS = [
  "full_name",
  "date_of_birth",
  "email",
  "phone",
  "highest_qualification",
  "institution",
  "graduation_year",
  "preferred_country",
  "preferred_course",
  "preferred_intake",
  "notes",
] as const;
export type FieldKey = (typeof FIELD_KEYS)[number];
export type FormValues = Record<FieldKey, string>;

export const NOTES_MAX = 2000;
const LIMITS: Partial<Record<FieldKey, number>> = {
  full_name: 160,
  email: 320,
  phone: 40,
  highest_qualification: 200,
  institution: 200,
  preferred_country: 120,
  preferred_course: 200,
  preferred_intake: 40,
  notes: NOTES_MAX,
};
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function emptyValues(): FormValues {
  return Object.fromEntries(FIELD_KEYS.map((k) => [k, ""])) as FormValues;
}

export function valuesFrom(d: AgentStudentDetail): FormValues {
  return Object.fromEntries(FIELD_KEYS.map((k) => [k, d[k] == null ? "" : String(d[k])])) as FormValues;
}

function normalise(key: FieldKey, raw: string): unknown {
  const value = raw.trim();
  if (!value) return null;
  if (key === "email") return value.toLowerCase();
  if (key === "graduation_year") return Number(value);
  return value;
}

// Create: every non-blank field. Edit (`original` given): only fields whose normalised value changed; a cleared field is null.
export function buildPayload(values: FormValues, original?: FormValues): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of FIELD_KEYS) {
    const next = normalise(key, values[key]);
    if (original) {
      if (next !== normalise(key, original[key])) out[key] = next;
    } else if (next !== null) {
      out[key] = next;
    }
  }
  return out;
}

export function validate(values: FormValues): Partial<Record<FieldKey, string>> {
  const errors: Partial<Record<FieldKey, string>> = {};
  for (const key of FIELD_KEYS) {
    const max = LIMITS[key];
    if (max && values[key].trim().length > max) errors[key] = `Must be ${max} characters or fewer`;
  }
  if (!values.full_name.trim()) errors.full_name = "Full name is required";
  if (values.email.trim() && !EMAIL.test(values.email.trim())) errors.email = "Enter a valid email address";
  if (values.date_of_birth) {
    const today = new Date().toISOString().slice(0, 10);
    if (values.date_of_birth > today || values.date_of_birth < "1900-01-01") errors.date_of_birth = "Date of birth must be between 1900 and today";
  }
  if (values.graduation_year.trim()) {
    const year = Number(values.graduation_year);
    const max = new Date().getFullYear() + 6;
    if (!Number.isInteger(year) || year < 1950 || year > max) errors.graduation_year = `Enter a year from 1950 to ${max}`;
  }
  return errors;
}

// The server's 409 `possible_duplicate` detail, or null for any other error (those go through apiErrors.detailMessage).
export function duplicateDetail(detail: unknown): DuplicateDetail | null {
  const d = detail as (Partial<DuplicateDetail> & { code?: string }) | null;
  if (!d || typeof d !== "object" || d.code !== "possible_duplicate" || !Array.isArray(d.matches)) return null;
  return { message: String(d.message ?? ""), matches: d.matches, hidden_matches: Number(d.hidden_matches ?? 0) };
}

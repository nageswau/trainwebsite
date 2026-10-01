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
  // AGN-006: always sent by the server; optional here so records built before AGN-006 (tests, fixtures) stay valid.
  counseling?: Counseling | null;
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
// AGN-005 QA5-01: the server's rule (schemas `_MOBILE`) -- digits, spaces, + - ( ), 7-20 characters, at least 7 digits.
const PHONE = /^[0-9+\-() ]{7,20}$/;
const PHONE_MESSAGE = "Enter a phone number of 7–20 digits, spaces, +, -, ( or ) with at least 7 digits";

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

// Edit (`original` given): an unchanged phone is not re-checked, because the server checks only a phone that is sent and a value
// saved before the AGN-005 rule must not block edits of other fields.
export function validate(values: FormValues, original?: FormValues): Partial<Record<FieldKey, string>> {
  const errors: Partial<Record<FieldKey, string>> = {};
  for (const key of FIELD_KEYS) {
    const max = LIMITS[key];
    if (max && values[key].trim().length > max) errors[key] = `Must be ${max} characters or fewer`;
  }
  if (!values.full_name.trim()) errors.full_name = "Full name is required";
  if (values.email.trim() && !EMAIL.test(values.email.trim())) errors.email = "Enter a valid email address";
  const phone = values.phone.trim();
  const phoneSent = !original || phone !== original.phone.trim();
  if (phone && phoneSent && (!PHONE.test(phone) || phone.replace(/\D/g, "").length < 7)) errors.phone = PHONE_MESSAGE;
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

// AGN-006 (DEC-SCOPE-048): the counseling record (EVID-015 §5 Step 2), replaced whole by PUT …/counseling. Mirrors
// schemas.AgentStudentCounselingSave; the server remains the authority.
export const CURRENCIES = ["INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD"] as const;
export type Currency = (typeof CURRENCIES)[number];
export type Counseling = {
  counseling_completed: boolean;
  completed_at: string | null;
  completed_by: string | null;
  career_interest: string | null;
  course_preference: string | null;
  country_preference: string | null;
  budget_amount: string | null;
  budget_currency: Currency | null;
  remarks: string | null;
  updated_at: string;
  updated_by: string | null;
};
export type CounselingValues = {
  counseling_completed: boolean;
  career_interest: string;
  course_preference: string;
  country_preference: string;
  budget_amount: string;
  budget_currency: Currency;
  remarks: string;
};
export type CounselingField = keyof CounselingValues;

const COUNSELING_LIMITS = { career_interest: 200, course_preference: 200, country_preference: 120, remarks: NOTES_MAX } as const;
const AMOUNT = /^\d{1,8}(\.\d{1,2})?$/; // 0 to 99,999,999.99 with at most 2 decimals (the server's bounds)

export function counselingUrl(id: string): string {
  return `${RECORDS_URL}/${id}/counseling`;
}

export function counselingValues(c?: Counseling | null): CounselingValues {
  return {
    counseling_completed: c?.counseling_completed ?? false,
    career_interest: c?.career_interest ?? "",
    course_preference: c?.course_preference ?? "",
    country_preference: c?.country_preference ?? "",
    budget_amount: c?.budget_amount ?? "",
    budget_currency: c?.budget_currency ?? "INR",
    remarks: c?.remarks ?? "",
  };
}

// "25,00,000" and "2 500 000" are what people type; the server gets digits only.
function plainAmount(value: string): string {
  return value.replace(/[,\s]/g, "");
}

export function counselingPayload(v: CounselingValues): Record<string, unknown> {
  const text = (s: string) => s.trim() || null;
  const amount = plainAmount(v.budget_amount);
  return {
    counseling_completed: v.counseling_completed,
    career_interest: text(v.career_interest),
    course_preference: text(v.course_preference),
    country_preference: text(v.country_preference),
    budget_amount: amount || null, // a string: no float rounding on the way
    budget_currency: amount ? v.budget_currency : null,
    remarks: text(v.remarks),
  };
}

export function validateCounseling(v: CounselingValues): Partial<Record<CounselingField, string>> {
  const errors: Partial<Record<CounselingField, string>> = {};
  for (const [key, max] of Object.entries(COUNSELING_LIMITS) as [keyof typeof COUNSELING_LIMITS, number][]) {
    if (v[key].trim().length > max) errors[key] = `Must be ${max} characters or fewer`;
  }
  const amount = plainAmount(v.budget_amount);
  if (amount.startsWith("-")) errors.budget_amount = "Budget cannot be negative";
  else if (amount && !AMOUNT.test(amount)) errors.budget_amount = "Enter an amount up to 99,999,999.99 with at most 2 decimals";
  return errors;
}

export function formatBudget(amount: string | null, currency: string | null): string {
  if (amount === null || !currency) return "—";
  try {
    return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-GB", { style: "currency", currency }).format(Number(amount));
  } catch {
    return `${currency} ${amount}`;
  }
}

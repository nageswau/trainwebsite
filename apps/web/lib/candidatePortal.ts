import type { NavItem } from "@/lib/navigation";

// hrc-022 (DEC-SCOPE-386): the external candidate portal -- registration, verification, the own profile with the allow-listed
// self-service fields (C7/C11), the verified email change (C9) and the pool consent (C12). The server decides everything; this file
// only shapes forms.
export const CANDIDATE_API = "/api/v1/candidate";
export const REGISTER_URL = `${CANDIDATE_API}/register`;
export const VERIFY_URL = `${CANDIDATE_API}/verify-email`;
export const RESEND_URL = `${CANDIDATE_API}/resend-verification`;
export const PROFILE_URL = `${CANDIDATE_API}/me`;
export const EMAIL_URL = `${CANDIDATE_API}/me/email`;
export const PRIVACY_URL = `${CANDIDATE_API}/me/privacy`;
export const SELF_SERVICE_SETTINGS_URL = "/api/v1/recruiter/candidate-self-service-settings";
export const CANDIDATE_PORTAL_HOME = "/it/careers/portal/profile";

export const CANDIDATE_NAV: NavItem[] = [
  { label: "Candidate profile", href: CANDIDATE_PORTAL_HOME },
  { label: "Privacy", href: "/it/careers/portal/privacy" },
];

// The wording the registration form shows; the server refuses any other version (C2).
export const CONSENT_VERSION = "candidate-v1";
export const CONSENT_TEXT =
  "I agree that EduSphere may keep my profile in its candidate pool and that its recruiters may contact me about jobs. I can leave " +
  "the pool at any time from Privacy; my existing applications continue.";

export type FieldKey =
  | "name" | "city" | "state" | "country" | "linkedin" | "current_company" | "notice_days" | "preferred_roles" | "tools" | "languages"
  | "available_from" | "willing_to_relocate" | "preferred_contact";

type FieldKind = "text" | "number" | "list" | "date" | "yesno" | "contact" | "url";
export const FIELDS: { key: FieldKey; label: string; kind: FieldKind; hint?: string }[] = [
  { key: "name", label: "Full name", kind: "text" },
  { key: "city", label: "City", kind: "text" },
  { key: "state", label: "State", kind: "text" },
  { key: "country", label: "Country", kind: "text" },
  { key: "current_company", label: "Current company", kind: "text" },
  { key: "notice_days", label: "Notice period (days)", kind: "number" },
  { key: "available_from", label: "Available from", kind: "date" },
  { key: "preferred_roles", label: "Preferred roles", kind: "list", hint: "Separate with commas" },
  { key: "tools", label: "Tools", kind: "list", hint: "Separate with commas" },
  { key: "languages", label: "Languages", kind: "list", hint: "Separate with commas" },
  { key: "willing_to_relocate", label: "Willing to relocate", kind: "yesno" },
  { key: "preferred_contact", label: "Preferred contact", kind: "contact" },
  { key: "linkedin", label: "LinkedIn", kind: "url" },
];
export const CONTACT_OPTIONS = [{ value: "phone", label: "Phone" }, { value: "whatsapp", label: "WhatsApp" }, { value: "email", label: "Email" }];

export type FieldValue = string | number | boolean | string[] | null;
export type CandidateProfile = {
  candidate_code: string;
  name: string;
  email: string;
  email_verified: boolean;
  mobile: string | null;
  pending_email: string | null;
  fields: Record<FieldKey, FieldValue>;
  editable: FieldKey[];
};
export type ConsentEntry = { action: "opt_in" | "opt_out"; consent_version: string; created_at: string };
// hrc-035 (DEC-SCOPE-396 K6): the latest "delete my data" request; null = none asked for.
export type ErasureRequest = { status: "in_progress" | "rejected" | "fulfilled"; requested_at: string; decided_at: string | null; rejection_reason: string | null };
export type PrivacyState = { opted_in: boolean; consent: { version: string; text: string }; history: ConsentEntry[]; erasure?: ErasureRequest | null };
export const ERASURE_URL = "/api/v1/candidate/me/erasure-request";
export type SelfServiceSettings = { fields: FieldKey[]; available: FieldKey[]; can_edit: boolean };

export function labelOf(key: string): string {
  return FIELDS.find((f) => f.key === key)?.label ?? key;
}

// Every value as the text its input holds: lists comma-joined, booleans "yes"/"no", empty "".
export function toForm(fields: Record<FieldKey, FieldValue>): Record<FieldKey, string> {
  const form = {} as Record<FieldKey, string>;
  for (const { key } of FIELDS) {
    const value = fields[key];
    form[key] = Array.isArray(value) ? value.join(", ") : typeof value === "boolean" ? (value ? "yes" : "no") : value == null ? "" : String(value);
  }
  return form;
}

function parse(kind: FieldKind, text: string): FieldValue {
  const trimmed = text.trim();
  if (kind === "list") return trimmed ? trimmed.split(",").map((s) => s.trim()).filter(Boolean) : [];
  if (!trimmed) return null;
  if (kind === "number") return Number(trimmed);
  if (kind === "yesno") return trimmed === "yes";
  return trimmed;
}

// The PATCH body: only editable fields whose text differs from what was loaded (the server refuses anything else anyway).
export function changedFields(form: Record<FieldKey, string>, loaded: Record<FieldKey, FieldValue>, editable: FieldKey[]): Partial<Record<FieldKey, FieldValue>> {
  const before = toForm(loaded);
  const body: Partial<Record<FieldKey, FieldValue>> = {};
  for (const { key, kind } of FIELDS) {
    if (editable.includes(key) && form[key].trim() !== before[key].trim()) body[key] = parse(kind, form[key]);
  }
  return body;
}

export function displayValue(key: FieldKey, value: FieldValue): string {
  if (value == null || (Array.isArray(value) && value.length === 0) || value === "") return "Not provided";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (key === "preferred_contact") return CONTACT_OPTIONS.find((o) => o.value === value)?.label ?? String(value);
  return String(value);
}

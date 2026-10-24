// ccrm-013 (DEC-SCOPE-256): an application's university-side fields and its counselor-editable dates. Mirrors
// apps/api/app/application_fields.py; the server is the authority on every rule and each role's scope.
import { money } from "@/lib/applicationOffers";

export const CURRENCIES = ["INR", "GBP", "USD", "EUR", "CAD", "AUD", "NZD", "SGD", "AED"];
export const SCHOLARSHIP_STATUSES = ["none", "applied", "awarded", "declined"];
export const SCHOLARSHIP_LABELS: Record<string, string> = { none: "None", applied: "Applied", awarded: "Awarded", declined: "Declined" };

type Kind = "text" | "url" | "email" | "date" | "money" | "currency" | "scholarship";
// The form's fields in the server's DETAIL_FIELDS order, with their labels.
export const DETAIL_FIELDS: { name: string; label: string; kind: Kind }[] = [
  { name: "faculty", label: "Faculty", kind: "text" },
  { name: "campus", label: "Campus", kind: "text" },
  { name: "course_start_date", label: "Course start date", kind: "date" },
  { name: "university_portal_url", label: "University portal link", kind: "url" },
  { name: "university_contact_name", label: "University contact name", kind: "text" },
  { name: "university_contact_email", label: "University contact email", kind: "email" },
  { name: "tuition_fee", label: "Tuition fee", kind: "money" },
  { name: "currency", label: "Currency", kind: "currency" },
  { name: "scholarship_status", label: "Scholarship", kind: "scholarship" },
  { name: "scholarship_amount", label: "Scholarship amount", kind: "money" },
  { name: "submitted_on", label: "Submitted on", kind: "date" },
  { name: "application_deadline", label: "Application deadline", kind: "date" },
  { name: "offer_deadline", label: "Offer deadline", kind: "date" },
  { name: "documents_completed_on", label: "Documents completed on", kind: "date" },
  { name: "decision_due_on", label: "Decision due on", kind: "date" },
];

export type ApplicationDetails = Record<string, string | number | null> & { id: string; application_code: string };
export type DetailsForm = Record<string, string>;

export const detailsUrl = (id: string) => `/api/v1/workflows/overseas/applications/${id}/details`;

const text = (value: string | number | null | undefined) => (value === null || value === undefined ? "" : String(value));

export function toForm(details: ApplicationDetails): DetailsForm {
  return Object.fromEntries(DETAIL_FIELDS.map(({ name }) => [name, text(details[name])]));
}

/** F3/F4, the server's rule repeated so the counselor hears it before sending. */
export function detailsProblem(form: DetailsForm): string | null {
  if (form.scholarship_amount?.trim() && form.scholarship_status !== "awarded") return "A scholarship amount is recorded only when the scholarship is awarded";
  if ((form.tuition_fee?.trim() || form.scholarship_amount?.trim()) && !form.currency) return "Currency is required with a tuition fee or a scholarship amount";
  return null;
}

/** The PATCH body: only the fields that differ from what was loaded; a blank field is null (clears it). */
export function changedFields(form: DetailsForm, loaded: Record<string, string | number | null>): Record<string, string | null> {
  const body: Record<string, string | null> = {};
  for (const [name, raw] of Object.entries(form)) {
    const value = raw.trim();
    const before = text(loaded[name]);
    const same = DETAIL_FIELDS.find((f) => f.name === name)?.kind === "money" ? value !== "" && before !== "" && Number(value) === Number(before) : value === before;
    if (!same && !(value === "" && before === "")) body[name] = value || null;
  }
  return body;
}

export function scholarshipText(details: Record<string, string | number | null>): string | null {
  const status = details.scholarship_status;
  if (!status) return null;
  const amount = details.scholarship_amount;
  const label = SCHOLARSHIP_LABELS[String(status)] ?? String(status);
  return amount === null || amount === undefined ? label : `${label} — ${money(text(details.currency) || null, String(amount))}`;
}

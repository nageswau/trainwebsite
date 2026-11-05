// rec-004 (DEC-SCOPE-125): a company's contacts -- types, endpoints and the pure helpers the Contacts section and the "+ Add Recruiter"
// form share. The API scopes every list and decides `can_edit`; nothing here filters for security.
import { detailMessage } from "@/lib/apiErrors";
import { COMPANIES_URL, type Ref } from "@/lib/recruiterCompanies";

export type Channel = "call" | "whatsapp" | "email" | "linkedin";
// pob-005 (DEC-SCOPE-411): "Follow-up due" is not a stored status -- the API derives `follow_up_due`.
export type ContactStatus = "not_contacted" | "contacted" | "replied" | "meeting_scheduled" | "not_interested" | "do_not_contact";
export type ContactSource = "linkedin" | "company_website" | "referral" | "job_portal" | "event" | "inbound" | "other";
export type Contact = {
  id: string; name: string; designation: string | null; department: string | null; role: Ref | null; mobile: string | null;
  email: string | null; linkedin_url: string | null; preferred_channel: Channel | null; notes: string | null; is_primary: boolean;
  active: boolean; last_contacted_at: string | null; next_follow_up_at?: string | null; created_at: string; updated_at: string;
  whatsapp_to?: string | null; // rec-026: the wa.me number (E.164 digits)
  // pob-005: optional so older fixtures and the "+ Add Recruiter" flow keep working
  is_decision_maker?: boolean; source?: ContactSource | null; verified_on?: string | null; status?: ContactStatus; follow_up_due?: boolean;
};
export type ContactList = { items: Contact[]; can_edit: boolean };

export const CONTACTS_URL = "/api/v1/recruiter/contacts";
export const contactsOf = (companyId: string) => `${COMPANIES_URL}/${companyId}/contacts`;
export const CHANNELS: Channel[] = ["call", "whatsapp", "email", "linkedin"];
export const CHANNEL_LABEL: Record<Channel, string> = { call: "Call", whatsapp: "WhatsApp", email: "Email", linkedin: "LinkedIn" };
export const STATUSES: ContactStatus[] = ["not_contacted", "contacted", "replied", "meeting_scheduled", "not_interested", "do_not_contact"];
export const STATUS_LABEL: Record<ContactStatus, string> = {
  not_contacted: "Not contacted", contacted: "Contacted", replied: "Replied", meeting_scheduled: "Meeting scheduled", not_interested: "Not interested",
  do_not_contact: "Do not contact",
};
export const SOURCES: ContactSource[] = ["linkedin", "company_website", "referral", "job_portal", "event", "inbound", "other"];
export const SOURCE_LABEL: Record<ContactSource, string> = {
  linkedin: "LinkedIn", company_website: "Company website", referral: "Referral", job_portal: "Job portal", event: "Event", inbound: "They contacted us",
  other: "Other",
};
export const contactTimelineUrl = (companyId: string, contactId: string) => `${COMPANIES_URL}/${companyId}/timeline?contact_id=${encodeURIComponent(contactId)}`;
export const contactFollowUpsUrl = (companyId: string, contactId: string) => `${COMPANIES_URL}/${companyId}/follow-ups?contact_id=${encodeURIComponent(contactId)}&limit=50`;

/** pob-005 D8: other contacts with this mobile or email -- in-scope ones named, the rest only counted. A warning, never a refusal. */
export type DuplicateMatch = { id: string; name: string; active: boolean; company: { id: string; name: string }; same_company: boolean; on: ("mobile" | "email")[] };
export type Duplicates = { matches: DuplicateMatch[]; others: number };
export function duplicatesUrl(companyId: string, values: { mobile: string; email: string }, exclude?: string): string | null {
  const params = new URLSearchParams();
  if (values.mobile.trim()) params.set("mobile", values.mobile.trim());
  if (values.email.trim()) params.set("email", values.email.trim());
  if (![...params.keys()].length) return null;
  if (exclude) params.set("exclude", exclude);
  return `${contactsOf(companyId)}/duplicates?${params}`;
}

/** Screen order (EVID-018 §4). The §2 person fields are the first ones "+ Add Recruiter" asks for. */
export const CONTACT_FIELDS = [
  "name", "designation", "department", "role_id", "mobile", "email", "linkedin_url", "preferred_channel", "is_decision_maker", "source", "verified_on", "status", "notes",
] as const;
export const RECRUITER_FIELDS: ContactField[] = ["name", "designation", "role_id", "mobile", "email", "linkedin_url"];
export type ContactField = (typeof CONTACT_FIELDS)[number];
export type ContactValues = Record<ContactField, string>;
export type ContactErrors = Partial<Record<ContactField, string>>;

export function contactValuesOf(c?: Contact): ContactValues {
  const text = (v: string | null | undefined) => v ?? "";
  return {
    name: text(c?.name), designation: text(c?.designation), department: text(c?.department), role_id: text(c?.role?.id), mobile: text(c?.mobile),
    email: text(c?.email), linkedin_url: text(c?.linkedin_url), preferred_channel: text(c?.preferred_channel), notes: text(c?.notes),
    is_decision_maker: c?.is_decision_maker ? "true" : "", source: text(c?.source), verified_on: text(c?.verified_on), status: c?.status ?? "not_contacted",
  };
}

/** Create: every filled field. Edit: only the fields that changed; blank is null (clears). */
export function contactBody(values: ContactValues, original?: ContactValues): Record<string, string | boolean | null> {
  // pob-005: a new contact's default status is the server's, so it is sent only when changed; the decision-maker box is a boolean
  const unchanged = (k: ContactField) => (original ? values[k] === original[k] : values[k].trim() === "" || (k === "status" && values[k] === "not_contacted"));
  const keys = CONTACT_FIELDS.filter((k) => !unchanged(k));
  return Object.fromEntries(keys.map((k) => [k, k === "is_decision_maker" ? values[k] === "true" : values[k].trim() === "" ? null : values[k].trim()]));
}

export function isContactList(data: unknown): data is ContactList {
  return Array.isArray((data as ContactList | null)?.items);
}

/** FastAPI's 422 list -> errors at the contact fields under `where` (["body"] for the Contacts section, ["body", "contact"] for "+ Add
 * Recruiter"); null when any item is about something else (then one message shows it all). */
export function contactErrorsOf(detail: unknown, where: string[]): ContactErrors | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const found: ContactErrors = {};
  for (const item of detail as { loc?: unknown[] }[]) {
    const loc = item?.loc ?? [];
    const field = loc[where.length] as ContactField;
    if (loc.length !== where.length + 1 || where.some((w, i) => loc[i] !== w) || !CONTACT_FIELDS.includes(field)) return null;
    found[field] = detailMessage([item]);
  }
  return found;
}

const HR_ROLES = ["hr manager", "hr head"];
const roleIs = (c: Contact, names: string[]) => !!c.role && names.includes(c.role.name.trim().toLowerCase());

/** C5: EVID-018 §3 Business Details, read from the active contacts by their seeded role names. HR email and phone are the primary
 * contact's when the primary holds an HR role, else the first HR contact's (the list is primary first, then insertion order). */
export function businessContacts(items: Contact[]) {
  const active = items.filter((c) => c.active);
  const hr = active.filter((c) => roleIs(c, HR_ROLES));
  const lead = hr[0] ?? null;
  return {
    hr,
    talentAcquisition: active.filter((c) => roleIs(c, ["talent acquisition manager"])),
    hiringManager: active.filter((c) => roleIs(c, ["hiring manager"])),
    hrEmail: lead?.email ?? null,
    hrPhone: lead?.mobile ?? null,
  };
}

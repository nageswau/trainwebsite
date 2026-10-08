// rec-004 (DEC-SCOPE-125): a company's contacts -- types, endpoints and the pure helpers the Contacts section and the "+ Add Recruiter"
// form share. The API scopes every list and decides `can_edit`; nothing here filters for security.
import { detailMessage } from "@/lib/apiErrors";
import { COMPANIES_URL, type Ref } from "@/lib/recruiterCompanies";

export type Channel = "call" | "whatsapp" | "email";
export type Contact = {
  id: string; name: string; designation: string | null; department: string | null; role: Ref | null; mobile: string | null;
  email: string | null; linkedin_url: string | null; preferred_channel: Channel | null; notes: string | null; is_primary: boolean;
  active: boolean; last_contacted_at: string | null; created_at: string; updated_at: string;
};
export type ContactList = { items: Contact[]; can_edit: boolean };

export const CONTACTS_URL = "/api/v1/recruiter/contacts";
export const contactsOf = (companyId: string) => `${COMPANIES_URL}/${companyId}/contacts`;
export const CHANNELS: Channel[] = ["call", "whatsapp", "email"];
export const CHANNEL_LABEL: Record<Channel, string> = { call: "Call", whatsapp: "WhatsApp", email: "Email" };

/** Screen order (EVID-018 §4). The §2 person fields are the first ones "+ Add Recruiter" asks for. */
export const CONTACT_FIELDS = ["name", "designation", "department", "role_id", "mobile", "email", "linkedin_url", "preferred_channel", "notes"] as const;
export const RECRUITER_FIELDS: ContactField[] = ["name", "designation", "role_id", "mobile", "email", "linkedin_url"];
export type ContactField = (typeof CONTACT_FIELDS)[number];
export type ContactValues = Record<ContactField, string>;
export type ContactErrors = Partial<Record<ContactField, string>>;

export function contactValuesOf(c?: Contact): ContactValues {
  const text = (v: string | null | undefined) => v ?? "";
  return {
    name: text(c?.name), designation: text(c?.designation), department: text(c?.department), role_id: text(c?.role?.id), mobile: text(c?.mobile),
    email: text(c?.email), linkedin_url: text(c?.linkedin_url), preferred_channel: text(c?.preferred_channel), notes: text(c?.notes),
  };
}

/** Create: every filled field. Edit: only the fields that changed; blank is null (clears). */
export function contactBody(values: ContactValues, original?: ContactValues): Record<string, string | null> {
  const keys = CONTACT_FIELDS.filter((k) => (original ? values[k] !== original[k] : values[k].trim() !== ""));
  return Object.fromEntries(keys.map((k) => [k, values[k].trim() === "" ? null : values[k].trim()]));
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

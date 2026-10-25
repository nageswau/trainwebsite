"use client";

import { formatCalendarDate, formatDate } from "@/lib/formatDate";
import { CONTACT_PREFERENCES, consentLabel, type LeadContact } from "@/lib/telecallerLeads";

// ccrm-005 (DEC-SCOPE-260; LF1, LF4-LF7): the spec §3 contact, consent and referral fields -- one group for the New Lead form, the
// telecaller's Lead details edit and the counselor's. A draft holds strings ("" = none; consent "yes" / "no" / "" = not asked); the API
// checks every value (none is mandatory, LF2).
export const CONTACT_KEYS = ["contact_preference", "enquiry_date", "marketing_opt_in", "referral_name", "referral_contact"] as const;
export type ContactKey = (typeof CONTACT_KEYS)[number];
export type ContactDraft = Record<ContactKey, string>;
export const EMPTY_CONTACT: ContactDraft = { contact_preference: "", enquiry_date: "", marketing_opt_in: "", referral_name: "", referral_contact: "" };

export const contactDraft = (lead: LeadContact): ContactDraft => ({
  contact_preference: lead.contact_preference ?? "", enquiry_date: lead.enquiry_date ?? "",
  marketing_opt_in: lead.marketing_opt_in === null ? "" : lead.marketing_opt_in ? "yes" : "no",
  referral_name: lead.referral_name ?? "", referral_contact: lead.referral_contact ?? "",
});

/** The API value of one draft entry: consent as true / false / null, any other blank as null. */
export function contactValue(key: ContactKey, text: string): string | boolean | null {
  const value = text.trim();
  if (key === "marketing_opt_in") return value === "" ? null : value === "yes";
  return value || null;
}

/** Only what differs from the lead (an edit sends changes only, tel-008 D2); the enquiry date is never cleared. */
export function contactChanges(draft: ContactDraft, lead: LeadContact): Partial<Record<ContactKey, string | boolean | null>> {
  const before = contactDraft(lead);
  return Object.fromEntries(CONTACT_KEYS.filter((key) => draft[key].trim() !== before[key] && !(key === "enquiry_date" && !draft[key]))
    .map((key) => [key, contactValue(key, draft[key])]));
}

/** The view rows for a lead's Lead details list. */
export function contactRows(lead: LeadContact): [string, React.ReactNode][] {
  const none = <span className="muted">—</span>;
  return [
    ["Enquiry date", formatCalendarDate(lead.enquiry_date)],
    ["Preferred contact", lead.contact_preference ? CONTACT_PREFERENCES[lead.contact_preference] ?? lead.contact_preference : none],
    ["Marketing consent", lead.marketing_consent_at ? `${consentLabel(lead.marketing_opt_in)} · ${formatDate(lead.marketing_consent_at)}` : consentLabel(lead.marketing_opt_in)],
    ["Referred by", lead.referral_name || lead.referral_contact ? [lead.referral_name, lead.referral_contact].filter(Boolean).join(" · ") : none],
  ];
}

const today = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
};

export default function LeadContactFields({ values, onChange, disabled, idPrefix }: {
  values: ContactDraft; onChange: (key: ContactKey, value: string) => void; disabled: boolean; idPrefix: string;
}) {
  const id = (key: ContactKey) => `${idPrefix}-${key}`;
  return (
    <>
      <div className="field">
        <label htmlFor={id("contact_preference")}>Preferred contact method</label>
        <select id={id("contact_preference")} value={values.contact_preference} disabled={disabled} onChange={(e) => onChange("contact_preference", e.target.value)}>
          <option value="">Not recorded</option>
          {Object.entries(CONTACT_PREFERENCES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor={id("enquiry_date")}>Enquiry date</label>
        <input id={id("enquiry_date")} type="date" min="2000-01-01" max={today()} aria-describedby={`${id("enquiry_date")}-help`} value={values.enquiry_date}
          disabled={disabled} onChange={(e) => onChange("enquiry_date", e.target.value)} />
        <span id={`${id("enquiry_date")}-help`} className="muted" style={{ fontSize: 13 }}>Leave blank for today.</span>
      </div>
      <div className="field">
        <label htmlFor={id("marketing_opt_in")}>Marketing consent</label>
        <select id={id("marketing_opt_in")} value={values.marketing_opt_in} disabled={disabled} onChange={(e) => onChange("marketing_opt_in", e.target.value)}>
          <option value="">Not asked</option>
          <option value="yes">Yes — agreed to marketing messages</option>
          <option value="no">No — no marketing messages</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor={id("referral_name")}>Referred by (name)</label>
        <input id={id("referral_name")} maxLength={160} value={values.referral_name} disabled={disabled} onChange={(e) => onChange("referral_name", e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor={id("referral_contact")}>Referrer&apos;s phone or email</label>
        <input id={id("referral_contact")} maxLength={120} value={values.referral_contact} disabled={disabled} onChange={(e) => onChange("referral_contact", e.target.value)} />
      </div>
    </>
  );
}

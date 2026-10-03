"use client";
import { useRef } from "react";

import { CHECKBOX_ROW, CONTACT_ROLE_LABEL, MAX_CONTACTS, rolesFor } from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-002 C1: an organization is created with at least one contact (at most 20) and exactly one primary (a radio group).
// Focus follows add and remove, so a keyboard user never lands on a control that disappeared (spec §12.2 F6).
export type ContactDraft = { name: string; designation: string; role: string; phone: string; email: string };
export type ContactField = keyof ContactDraft;
export type ContactValues = ContactDraft & { key: string; is_primary: boolean };
export const blankContact = (key: string, primary = false): ContactValues => ({ key, name: "", designation: "", role: "", phone: "", email: "", is_primary: primary });

/** One contact's five inputs, shared by the create form and the contact editor. Ids are `${idBase}-${field}`. bdm-003 P8: the
 * organization type's named people (Principal, Dean ... Owner) come first in Role; every role stays available. */
export function ContactInputs({
  idBase,
  values,
  errors,
  onChange,
  orgType,
  autoFocusName = false,
}: {
  idBase: string;
  values: ContactDraft;
  errors: Partial<Record<ContactField, string>>;
  onChange: (field: ContactField, value: string) => void;
  orgType?: string;
  autoFocusName?: boolean;
}) {
  const id = (field: ContactField) => `${idBase}-${field}`;
  const invalid = (field: ContactField) => (errors[field] ? { "aria-invalid": true, "aria-describedby": `${id(field)}-error` } : {});
  const error = (field: ContactField) =>
    errors[field] ? (
      <p className="form-error" id={`${id(field)}-error`}>
        {errors[field]}
      </p>
    ) : null;
  const text = (field: "designation" | "phone" | "email", label: string, type: string, autoComplete: string, maxLength: number) => (
    <div className="field">
      <label htmlFor={id(field)}>{label}</label>
      <input id={id(field)} type={type} autoComplete={autoComplete} maxLength={maxLength} value={values[field]} {...invalid(field)} onChange={(e) => onChange(field, e.target.value)} />
      {error(field)}
    </div>
  );
  return (
    <>
      <div className="field">
        <label htmlFor={id("name")}>Contact name (required)</label>
        <input id={id("name")} autoFocus={autoFocusName} autoComplete="name" maxLength={200} value={values.name} aria-required="true" {...invalid("name")} onChange={(e) => onChange("name", e.target.value)} />
        {error("name")}
      </div>
      {text("designation", "Designation", "text", "organization-title", 120)}
      <div className="field">
        <label htmlFor={id("role")}>Role</label>
        <select id={id("role")} value={values.role} onChange={(e) => onChange("role", e.target.value)}>
          <option value="">Not set</option>
          {rolesFor(orgType).map((r) => (
            <option key={r} value={r}>
              {CONTACT_ROLE_LABEL[r]}
            </option>
          ))}
        </select>
      </div>
      {text("phone", "Phone", "tel", "tel", 30)}
      {text("email", "Email", "email", "email", 255)}
    </>
  );
}

export default function BdmContactFields({
  idPrefix,
  contacts,
  errors,
  onChange,
  orgType,
}: {
  idPrefix: string;
  contacts: ContactValues[];
  errors: Record<string, string>;
  onChange: (contacts: ContactValues[]) => void;
  orgType?: string;
}) {
  const focus = useFocusAfterRender();
  // A per-form counter: the same on the server and in the browser (browser QA-09) and never reused after a remove, so a new row
  // can't inherit a removed row's error (simplify review A4).
  const lastKey = useRef(contacts.length);
  const nameId = (c: ContactValues) => `${idPrefix}-${c.key}-name`;
  const set = (key: string, patch: Partial<ContactValues>) => onChange(contacts.map((c) => (c.key === key ? { ...c, ...patch } : c)));
  const add = () => {
    lastKey.current += 1;
    const added = blankContact(`c${lastKey.current}`);
    onChange([...contacts, added]);
    focus(nameId(added));
  };
  const remove = (index: number) => {
    const rest = contacts.filter((_, i) => i !== index);
    if (contacts[index].is_primary) rest[0] = { ...rest[0], is_primary: true };
    onChange(rest);
    focus(nameId(rest[Math.max(0, index - 1)]));
  };
  const errorsOf = (c: ContactValues) => Object.fromEntries(Object.entries(errors).filter(([k]) => k.startsWith(`${c.key}-`)).map(([k, v]) => [k.slice(c.key.length + 1), v]));
  return (
    <fieldset className="form" style={{ border: 0, padding: 0, margin: 0 }}>
      <legend style={{ fontWeight: 800 }}>Contacts</legend>
      {contacts.map((c, i) => (
        <fieldset key={c.key} className="form" style={{ border: "1px solid var(--line)", borderRadius: 12, padding: 14 }}>
          <legend style={{ fontWeight: 800, padding: "0 6px" }}>
            Contact {i + 1}
            {c.is_primary ? " (primary)" : ""}
          </legend>
          <ContactInputs idBase={`${idPrefix}-${c.key}`} values={c} errors={errorsOf(c)} onChange={(field, value) => set(c.key, { [field]: value })} orgType={orgType} />
          <label style={CHECKBOX_ROW}>
            <input type="radio" name={`${idPrefix}-primary`} checked={c.is_primary} onChange={() => onChange(contacts.map((x) => ({ ...x, is_primary: x.key === c.key })))} />
            Primary contact
          </label>
          {contacts.length > 1 && (
            <button type="button" className="btn secondary small" onClick={() => remove(i)}>
              Remove contact {i + 1}
            </button>
          )}
        </fieldset>
      ))}
      <div>
        <button type="button" className="btn secondary small" onClick={add} disabled={contacts.length >= MAX_CONTACTS}>
          Add contact
        </button>
        {contacts.length >= MAX_CONTACTS && <p className="muted">An organization can have at most {MAX_CONTACTS} contacts.</p>}
      </div>
    </fieldset>
  );
}

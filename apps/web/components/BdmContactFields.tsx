"use client";
import { CONTACT_ROLE_LABEL, CONTACT_ROLES } from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-002 C1: an organization is created with at least one contact (at most 20) and exactly one primary (a radio group).
// Focus follows add and remove, so a keyboard user never lands on a control that disappeared (spec §12.2 F6).
export type ContactValues = { key: string; name: string; designation: string; role: string; phone: string; email: string; is_primary: boolean };
export const MAX_CONTACTS = 20;
let next = 0;
export const blankContact = (primary = false): ContactValues => ({ key: `c${++next}`, name: "", designation: "", role: "", phone: "", email: "", is_primary: primary });

export default function BdmContactFields({
  idPrefix,
  contacts,
  errors,
  onChange,
}: {
  idPrefix: string;
  contacts: ContactValues[];
  errors: Record<string, string>;
  onChange: (contacts: ContactValues[]) => void;
}) {
  const focus = useFocusAfterRender();
  const id = (c: ContactValues, field: string) => `${idPrefix}-${c.key}-${field}`;
  const invalid = (c: ContactValues, field: string) => {
    const message = errors[`${c.key}-${field}`];
    return message ? { "aria-invalid": true, "aria-describedby": `${id(c, field)}-error` } : {};
  };
  const errorOf = (c: ContactValues, field: string) =>
    errors[`${c.key}-${field}`] ? (
      <p className="form-error" id={`${id(c, field)}-error`}>
        {errors[`${c.key}-${field}`]}
      </p>
    ) : null;
  const set = (key: string, patch: Partial<ContactValues>) => onChange(contacts.map((c) => (c.key === key ? { ...c, ...patch } : c)));
  const add = () => {
    const added = blankContact();
    onChange([...contacts, added]);
    focus(id(added, "name"));
  };
  const remove = (index: number) => {
    const rest = contacts.filter((_, i) => i !== index);
    if (contacts[index].is_primary) rest[0] = { ...rest[0], is_primary: true };
    onChange(rest);
    focus(id(rest[Math.max(0, index - 1)], "name"));
  };
  return (
    <fieldset className="form" style={{ border: 0, padding: 0, margin: 0 }}>
      <legend style={{ fontWeight: 800 }}>Contacts</legend>
      {contacts.map((c, i) => {
        const nameError = errors[`${c.key}-name`];
        return (
          <fieldset key={c.key} className="form" style={{ border: "1px solid var(--line)", borderRadius: 12, padding: 14 }}>
            <legend style={{ fontWeight: 800, padding: "0 6px" }}>
              Contact {i + 1}
              {c.is_primary ? " (primary)" : ""}
            </legend>
            <div className="field">
              <label htmlFor={id(c, "name")}>Contact name (required)</label>
              <input
                id={id(c, "name")}
                autoComplete="name"
                maxLength={200}
                value={c.name}
                aria-required="true"
                aria-invalid={nameError ? true : undefined}
                aria-describedby={nameError ? `${id(c, "name")}-error` : undefined}
                onChange={(e) => set(c.key, { name: e.target.value })}
              />
              {nameError && (
                <p className="form-error" id={`${id(c, "name")}-error`}>
                  {nameError}
                </p>
              )}
            </div>
            <div className="field">
              <label htmlFor={id(c, "designation")}>Designation</label>
              <input id={id(c, "designation")} autoComplete="organization-title" maxLength={120} value={c.designation} {...invalid(c, "designation")} onChange={(e) => set(c.key, { designation: e.target.value })} />
              {errorOf(c, "designation")}
            </div>
            <div className="field">
              <label htmlFor={id(c, "role")}>Role</label>
              <select id={id(c, "role")} value={c.role} onChange={(e) => set(c.key, { role: e.target.value })}>
                <option value="">Not set</option>
                {CONTACT_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {CONTACT_ROLE_LABEL[r]}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor={id(c, "phone")}>Phone</label>
              <input id={id(c, "phone")} type="tel" autoComplete="tel" maxLength={30} value={c.phone} {...invalid(c, "phone")} onChange={(e) => set(c.key, { phone: e.target.value })} />
              {errorOf(c, "phone")}
            </div>
            <div className="field">
              <label htmlFor={id(c, "email")}>Email</label>
              <input id={id(c, "email")} type="email" autoComplete="email" maxLength={255} value={c.email} {...invalid(c, "email")} onChange={(e) => set(c.key, { email: e.target.value })} />
              {errorOf(c, "email")}
            </div>
            <label style={{ display: "flex", gap: 6, alignItems: "center", minHeight: 44 }}>
              <input type="radio" name={`${idPrefix}-primary`} checked={c.is_primary} onChange={() => onChange(contacts.map((x) => ({ ...x, is_primary: x.key === c.key })))} />
              Primary contact
            </label>
            {contacts.length > 1 && (
              <button type="button" className="btn secondary small" onClick={() => remove(i)}>
                Remove contact {i + 1}
              </button>
            )}
          </fieldset>
        );
      })}
      <div>
        <button type="button" className="btn secondary small" onClick={add} disabled={contacts.length >= MAX_CONTACTS}>
          Add contact
        </button>
        {contacts.length >= MAX_CONTACTS && <p className="muted">An organization can have at most {MAX_CONTACTS} contacts.</p>}
      </div>
    </fieldset>
  );
}

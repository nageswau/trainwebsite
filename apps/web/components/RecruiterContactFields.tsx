"use client";
import type { CatalogueValue } from "@/lib/recruiterCatalogue";
import type { Ref } from "@/lib/recruiterCompanies";
import { CHANNEL_LABEL, CHANNELS, type ContactErrors, type ContactField, type ContactValues } from "@/lib/recruiterContacts";

// rec-004: one contact's inputs, shared by the Contacts section's editor and the "+ Add Recruiter" form. Ids are `${idPrefix}-${field}`,
// errors sit under their field (aria-describedby), and every rule is the server's -- the limits here only save a round trip.
type Text = { label: string; max: number; type?: string; autoComplete?: string; hint?: string; multiline?: boolean };
const TEXT: Partial<Record<ContactField, Text>> = {
  name: { label: "Contact name (required)", max: 200, autoComplete: "off" },
  designation: { label: "Designation", max: 120, autoComplete: "off" },
  department: { label: "Department", max: 120, autoComplete: "off" },
  mobile: { label: "Mobile", max: 40, type: "tel", autoComplete: "off", hint: "For example 98765 43210 or +44 20 7946 0958" },
  email: { label: "Email", max: 255, type: "email", autoComplete: "off" },
  linkedin_url: { label: "LinkedIn", max: 300, type: "url", autoComplete: "off", hint: "For example linkedin.com/in/name" },
  notes: { label: "Notes", max: 2000, multiline: true },
};

export default function RecruiterContactFields({
  idPrefix,
  fields,
  values,
  errors,
  roles,
  currentRole,
  onChange,
  autoFocusName = false,
}: {
  idPrefix: string;
  fields: readonly ContactField[];
  values: ContactValues;
  errors: ContactErrors;
  /** The active contact roles; a stored role that has since been deactivated stays selectable (keeping it is allowed). */
  roles: CatalogueValue[];
  currentRole?: Ref | null;
  onChange: (field: ContactField, value: string) => void;
  autoFocusName?: boolean;
}) {
  const id = (field: ContactField) => `${idPrefix}-${field}`;
  const describedBy = (field: ContactField) => [errors[field] && `${id(field)}-error`, TEXT[field]?.hint && `${id(field)}-hint`].filter(Boolean).join(" ") || undefined;
  const roleOptions = currentRole && !roles.some((r) => r.id === currentRole.id) ? [...roles, { id: currentRole.id, name: `${currentRole.name} (inactive)` }] : roles;

  function field(key: ContactField) {
    const common = { id: id(key), value: values[key], "aria-invalid": errors[key] ? true : undefined, "aria-describedby": describedBy(key) };
    const spec = TEXT[key];
    let control;
    if (key === "role_id" || key === "preferred_channel") {
      const options = key === "role_id" ? roleOptions.map((r) => ({ id: r.id, name: r.name })) : CHANNELS.map((c) => ({ id: c, name: CHANNEL_LABEL[c] }));
      control = (
        <select {...common} onChange={(e) => onChange(key, e.target.value)}>
          <option value="">Not set</option>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>
      );
    } else if (spec?.multiline) {
      control = <textarea {...common} rows={3} maxLength={spec.max} onChange={(e) => onChange(key, e.target.value)} />;
    } else {
      control = (
        <input
          {...common}
          type={spec?.type === "email" ? "email" : "text"}
          inputMode={spec?.type === "tel" ? "tel" : spec?.type === "url" ? "url" : undefined}
          autoComplete={spec?.autoComplete}
          maxLength={spec?.max}
          autoFocus={key === "name" && autoFocusName}
          aria-required={key === "name" ? true : undefined}
          onChange={(e) => onChange(key, e.target.value)}
        />
      );
    }
    return (
      <div className="field" key={key}>
        <label htmlFor={id(key)}>{key === "role_id" ? "Role" : key === "preferred_channel" ? "Preferred communication" : spec?.label}</label>
        {control}
        {spec?.hint && (
          <p className="muted field-help" id={`${id(key)}-hint`}>
            {spec.hint}
          </p>
        )}
        {errors[key] && (
          <p className="form-error" id={`${id(key)}-error`}>
            {errors[key]}
          </p>
        )}
      </div>
    );
  }

  const short = fields.filter((f) => f !== "notes");
  return (
    <>
      <div className="form-grid">{short.map(field)}</div>
      {fields.includes("notes") && field("notes")}
    </>
  );
}

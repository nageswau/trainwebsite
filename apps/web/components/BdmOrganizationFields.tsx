"use client";
import { Fragment } from "react";

import { CHECKBOX_ROW, ORG_TYPE_LABEL, ORG_TYPES } from "@/lib/bdmOrganizations";

// bdm-002 §9 fields (spec §12.2 F5): visible labels with "(required)" in the text, typed inputs, and each field's error tied to it
// by aria-describedby. The parent form owns the values and the errors.
export type OrgValues = {
  org_type: string;
  name: string;
  city: string;
  state: string;
  address: string;
  phone: string;
  email: string;
  website: string;
  existing_partner: boolean;
  courses_interested: string;
  student_count: string;
};
export type OrgField = keyof OrgValues;
/** Every organization field, in form order: the one list the form sends, diffs and maps server errors onto. */
export const ORG_FIELDS: OrgField[] = ["org_type", "name", "city", "state", "address", "phone", "email", "website", "existing_partner", "courses_interested", "student_count"];
type TextField = {
  key: Exclude<OrgField, "org_type" | "existing_partner" | "courses_interested" | "address">;
  label: string;
  required?: true;
  type?: string;
  inputMode?: "numeric";
  autoComplete?: string;
  max: number;
};
const TEXT_FIELDS: TextField[] = [
  { key: "name", label: "Organization name", required: true, autoComplete: "organization", max: 200 },
  { key: "city", label: "City", required: true, autoComplete: "address-level2", max: 120 },
  { key: "state", label: "State", autoComplete: "address-level1", max: 120 },
  { key: "phone", label: "Phone", type: "tel", autoComplete: "tel", max: 30 },
  { key: "email", label: "Email", type: "email", autoComplete: "email", max: 255 },
  { key: "website", label: "Website", type: "url", autoComplete: "url", max: 255 },
  { key: "student_count", label: "Number of students", type: "number", inputMode: "numeric", max: 1_000_000 },
];

export default function BdmOrganizationFields({
  idPrefix,
  values,
  errors,
  onChange,
}: {
  idPrefix: string;
  values: OrgValues;
  errors: Partial<Record<OrgField, string>>;
  onChange: (key: OrgField, value: string | boolean) => void;
}) {
  const errorId = (key: OrgField) => `${idPrefix}-${key}-error`;
  const describedBy = (key: OrgField, hint?: string) => [errors[key] ? errorId(key) : null, hint ?? null].filter(Boolean).join(" ") || undefined;
  const error = (key: OrgField) =>
    errors[key] ? (
      <p className="form-error" id={errorId(key)}>
        {errors[key]}
      </p>
    ) : null;
  // bdm-003 P14: line breaks are kept in Address and Courses interested.
  const multiline = (key: "address" | "courses_interested", label: string, max: number, autoComplete?: string) => (
    <div className="field">
      <label htmlFor={`${idPrefix}-${key}`}>{label}</label>
      <textarea
        id={`${idPrefix}-${key}`}
        maxLength={max}
        rows={3}
        autoComplete={autoComplete}
        value={values[key]}
        aria-invalid={errors[key] ? true : undefined}
        aria-describedby={describedBy(key)}
        onChange={(e) => onChange(key, e.target.value)}
      />
      {error(key)}
    </div>
  );
  return (
    <fieldset className="form" style={{ border: 0, padding: 0, margin: 0 }}>
      <legend className="visually-hidden">Organization</legend>
      <div className="field">
        <label htmlFor={`${idPrefix}-org_type`}>Type (required)</label>
        <select
          id={`${idPrefix}-org_type`}
          value={values.org_type}
          aria-required="true"
          aria-invalid={errors.org_type ? true : undefined}
          aria-describedby={describedBy("org_type", `${idPrefix}-org_type-hint`)}
          onChange={(e) => onChange("org_type", e.target.value)}
        >
          <option value="">Choose a type</option>
          {ORG_TYPES.map((t) => (
            <option key={t} value={t}>
              {ORG_TYPE_LABEL[t]}
            </option>
          ))}
        </select>
        <p className="muted field-help" id={`${idPrefix}-org_type-hint`}>
          The details section below changes with the type.
        </p>
        {error("org_type")}
      </div>
      {TEXT_FIELDS.map((f) => {
        const numeric = f.type === "number";
        const hint = f.key === "website" ? `${idPrefix}-website-hint` : undefined;
        return (
          <Fragment key={f.key}>
            <div className="field">
              <label htmlFor={`${idPrefix}-${f.key}`}>
                {f.label}
                {f.required && " (required)"}
              </label>
              <input
                id={`${idPrefix}-${f.key}`}
                type={f.type ?? "text"}
                inputMode={f.inputMode}
                autoComplete={f.autoComplete}
                maxLength={numeric ? undefined : f.max}
                min={numeric ? 0 : undefined}
                max={numeric ? f.max : undefined}
                value={values[f.key]}
                aria-required={f.required}
                aria-invalid={errors[f.key] ? true : undefined}
                aria-describedby={describedBy(f.key, hint)}
                onChange={(e) => onChange(f.key, e.target.value)}
              />
              {hint && (
                <p className="muted field-help" id={hint}>
                  For example stjoseph.edu or https://stjoseph.edu
                </p>
              )}
              {error(f.key)}
            </div>
            {f.key === "state" && multiline("address", "Address", 500, "street-address")}
          </Fragment>
        );
      })}
      {multiline("courses_interested", "Courses interested", 1000)}
      <label style={CHECKBOX_ROW}>
        <input type="checkbox" checked={values.existing_partner} onChange={(e) => onChange("existing_partner", e.target.checked)} />
        Existing partner
      </label>
    </fieldset>
  );
}

"use client";
import type { ChangeEvent } from "react";

import {
  ALL_PROFILE_FIELDS,
  BOARD_LABEL,
  BOARDS,
  COLLEGE_TYPE_LABEL,
  COLLEGE_TYPES,
  gradeLabel,
  GRADES,
  type OrgProfile,
  PROFILE_FIELDS,
  PROFILE_GROUP_LABEL,
  PROFILE_LABEL,
  type ProfileField,
  type ProfileGroup,
  SCHOOL_TYPE_LABEL,
  SCHOOL_TYPES,
  SOURCE_LABEL,
  SOURCES,
} from "@/lib/bdmOrganizations";

// bdm-003 (spec §6.2): the type-specific fields of one organization, plus the profile's form logic (values, payload, checks), the way
// BdmContactFields owns blankContact -- so BdmOrganizationForm stays small (§12.2 F1). Only the current type's group is shown or sent.
export type ProfileValues = Record<ProfileField, string>;
type Errors = Partial<Record<ProfileField, string>>;
const NUMERIC: ProfileField[] = ["staff_count", "grade_from", "grade_to"];
const GRADE_ORDER = "Lowest grade can't be above the highest grade";

export function profileValuesOf(profile?: OrgProfile | null): ProfileValues {
  const values = Object.fromEntries(ALL_PROFILE_FIELDS.map((k) => [k, ""])) as ProfileValues;
  for (const [key, value] of Object.entries(profile ?? {})) if (key !== "kind" && value !== null) values[key as ProfileField] = String(value);
  return values;
}

/** Blank is null (clears on edit); a whole number is a number; anything else goes as typed, so the server's plain 422 names the field
 * (Number("abc") is NaN, which JSON would turn into a silent null -- Review Focus 2). */
function wire(key: ProfileField, value: string): unknown {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  return NUMERIC.includes(key) && /^-?\d+$/.test(trimmed) ? Number(trimmed) : trimmed;
}

/** Create (no `original`): the group's filled fields. Edit: the group's changed fields. Null when there is nothing to send. */
export function profilePayload(group: ProfileGroup | null, values: ProfileValues, original?: ProfileValues): Record<string, unknown> | null {
  if (!group) return null;
  const keys = PROFILE_FIELDS[group].filter((k) => (original ? values[k].trim() !== original[k].trim() : values[k].trim() !== ""));
  return keys.length ? Object.fromEntries(keys.map((k) => [k, wire(k, values[k])])) : null;
}

/** A convenience before sending (the server decides): the grade order. */
export function profileErrors(group: ProfileGroup | null, values: ProfileValues): Errors {
  if (group !== "school" || values.grade_from === "" || values.grade_to === "") return {};
  return Number(values.grade_from) > Number(values.grade_to) ? { grade_to: GRADE_ORDER } : {};
}

export function filledFields(group: ProfileGroup | null, values: ProfileValues): ProfileField[] {
  return group ? PROFILE_FIELDS[group].filter((k) => values[k].trim() !== "") : [];
}

type Option = readonly [string, string];
type Spec = { key: ProfileField; kind: "text" | "number" | "textarea"; max: number } | { key: ProfileField; kind: "select"; options: Option[] };
const options = (values: readonly string[], labels: Record<string, string>): Option[] => values.map((v) => [v, labels[v]] as const);
const GRADE_OPTIONS: Option[] = GRADES.map((g) => [String(g), gradeLabel(g)] as const);
const SPECS: Record<ProfileGroup, Spec[]> = {
  agent: [
    { key: "country", kind: "text", max: 120 },
    { key: "territory", kind: "text", max: 120 },
    { key: "source", kind: "select", options: options(SOURCES, SOURCE_LABEL) },
    { key: "staff_count", kind: "number", max: 100_000 },
  ],
  school: [
    { key: "board", kind: "select", options: options(BOARDS, BOARD_LABEL) },
    { key: "school_type", kind: "select", options: options(SCHOOL_TYPES, SCHOOL_TYPE_LABEL) },
    { key: "grade_from", kind: "select", options: GRADE_OPTIONS },
    { key: "grade_to", kind: "select", options: GRADE_OPTIONS },
  ],
  college: [
    { key: "affiliation", kind: "text", max: 200 },
    { key: "college_type", kind: "select", options: options(COLLEGE_TYPES, COLLEGE_TYPE_LABEL) },
    { key: "courses", kind: "textarea", max: 1000 },
  ],
};

export default function BdmOrganizationProfileFields({
  idPrefix,
  group,
  values,
  errors,
  onChange,
}: {
  idPrefix: string;
  group: ProfileGroup | null;
  values: ProfileValues;
  errors: Errors;
  onChange: (key: ProfileField, value: string) => void;
}) {
  if (!group) return null;
  const field = (spec: Spec) => {
    const id = `${idPrefix}-${spec.key}`;
    const control = {
      id,
      value: values[spec.key],
      "aria-invalid": errors[spec.key] ? true : undefined,
      "aria-describedby": errors[spec.key] ? `${id}-error` : undefined,
      onChange: (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => onChange(spec.key, e.target.value),
    };
    return (
      <div className="field" key={spec.key}>
        <label htmlFor={id}>{PROFILE_LABEL[spec.key]}</label>
        {spec.kind === "select" ? (
          <select {...control}>
            <option value="">Choose…</option>
            {spec.options.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        ) : spec.kind === "textarea" ? (
          <textarea {...control} rows={3} maxLength={spec.max} />
        ) : spec.kind === "number" ? (
          <input {...control} type="number" inputMode="numeric" min={0} max={spec.max} />
        ) : (
          <input {...control} type="text" maxLength={spec.max} />
        )}
        {errors[spec.key] && (
          <p className="form-error" id={`${id}-error`}>
            {errors[spec.key]}
          </p>
        )}
      </div>
    );
  };
  return (
    <fieldset className="form" style={{ border: 0, padding: 0, margin: 0 }}>
      <legend style={{ fontWeight: 800 }}>{PROFILE_GROUP_LABEL[group]} details</legend>
      {SPECS[group].map(field)}
      {group === "agent" && (
        <p className="muted" style={{ margin: 0 }}>
          Commission: Available after onboarding
        </p>
      )}
    </fieldset>
  );
}

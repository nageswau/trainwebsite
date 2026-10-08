"use client";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import { activeValues, type CatalogueValue } from "@/lib/recruiterCatalogue";
import { recruiterSearch, type Ref } from "@/lib/recruiterCompanies";
import {
  companySearch,
  FORM_FIELDS,
  type FormField,
  isRequirementBody,
  label,
  monthsFromYears,
  type Requirement,
  requirementBody,
  REQUIREMENTS_URL,
  type StatusCatalogue,
  valuesOf,
} from "@/lib/recruiterRequirements";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

// rec-007 (spec §6): add or edit a job requirement (EVID-018 §6; the company contact who gave it arrives with rec-004). Skills are typed
// one per comma or line and matched against the Skills Master on the server -- an unmatched one is kept and flagged on the detail page.
// The entry is never cleared on an error, and every rule is the server's; the checks here only save a round trip.
const LEAVE_PROMPT = "You have unsaved changes to this requirement. Leave without saving?";
type Text = { label: string; max: number; multiline?: boolean; type?: "date" | "number"; hint?: string; required?: boolean };
const TEXT: Partial<Record<FormField, Text>> = {
  title: { label: "Job title", max: 180, required: true },
  department: { label: "Department", max: 120 },
  vacancies: { label: "Number of vacancies", max: 5 },
  qualification: { label: "Qualification", max: 300 },
  experience_min_months: { label: "Experience from (years)", max: 5, hint: "For example 0 or 1.5" },
  experience_max_months: { label: "Experience to (years)", max: 5 },
  salary_min: { label: "Salary from (₹ a year)", max: 13 },
  salary_max: { label: "Salary to (₹ a year)", max: 13 },
  location: { label: "Job location", max: 120, required: true },
  joining_requirement: { label: "Joining requirement", max: 300, hint: "For example Immediate, or within 30 days" },
  closes_on: { label: "Application deadline", max: 10, type: "date" },
  requirement_date: { label: "Requirement date", max: 10, type: "date", hint: "The day the requirement was received. Today if left empty." },
  required_skills: { label: "Required skills", max: 3000, multiline: true, hint: "One per comma or line" },
  preferred_skills: { label: "Preferred skills", max: 3000, multiline: true, hint: "One per comma or line" },
  description: { label: "Job description", max: 10000, multiline: true },
};
const SELECTS: Partial<Record<FormField, { label: string; vocabulary: string }>> = {
  work_mode: { label: "Work mode", vocabulary: "work_mode" },
  shift: { label: "Shift", vocabulary: "shift" },
  employment_type: { label: "Employment type", vocabulary: "employment_type" },
  priority: { label: "Priority", vocabulary: "priority" },
};
const SKILL_FIELDS = new Set<string>(["required_skills", "preferred_skills"]);

/** FastAPI's 422 list -> errors at the form's fields (a skill's item lands on its list); null when any item is about something else. */
function fieldErrors(detail: unknown): Partial<Record<FormField, string>> | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const found: Partial<Record<FormField, string>> = {};
  for (const item of detail as { loc?: unknown[] }[]) {
    const [where, field] = item?.loc ?? [];
    const onList = SKILL_FIELDS.has(field as string);
    if (where !== "body" || !FORM_FIELDS.includes(field as FormField) || (item.loc!.length !== 2 && !onList)) return null;
    found[field as FormField] = detailMessage([item]);
  }
  return found;
}

function withCurrent(options: { id: string; name: string }[], current: Ref | null | undefined) {
  return current && !options.some((o) => o.id === current.id) ? [...options, { id: current.id, name: `${current.name} (inactive)` }] : options;
}

export default function RecruiterRequirementForm({
  mode,
  requirement,
  company,
  canChooseRecruiter = false,
  onSaved,
  onCancel,
}: {
  mode: "create" | "edit";
  requirement?: Requirement;
  /** "+ Add Job Requirement" from a company page fixes the company; otherwise the user picks one. */
  company?: PickOption | null;
  /** Managers and super admin may hand the new requirement to a recruiter (else the company's recruiter gets it). */
  canChooseRecruiter?: boolean;
  onSaved: (r: Requirement, saved: boolean) => void;
  onCancel: () => void;
}) {
  const original = useRef(valuesOf(requirement));
  const [values, setValues] = useState(original.current);
  const [companyPick, setCompanyPick] = useState<PickOption | null>(company ?? null);
  const [recruiter, setRecruiter] = useState<string | null>(null);
  const [errors, setErrors] = useState<Partial<Record<FormField | "company", string>>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [categories, setCategories] = useState<CatalogueValue[]>([]);
  const [vocabularies, setVocabularies] = useState<Record<string, string[]>>({});
  const [pickersFailed, setPickersFailed] = useState(false);
  const focus = useFocusAfterRender();
  const idPrefix = mode === "create" ? "requirement-new" : `requirement-${requirement?.id}`;
  const dirty = FORM_FIELDS.some((k) => values[k] !== original.current[k]) || recruiter !== null || (mode === "create" && !company && companyPick !== null);
  const searchRecruiters = useMemo(() => recruiterSearch(null), []);
  useLeaveGuard(dirty, LEAVE_PROMPT);

  useEffect(() => {
    const abort = new AbortController();
    Promise.all([activeValues("job-categories", abort.signal), fetch(`${REQUIREMENTS_URL}/statuses`, { signal: abort.signal }).then((r) => (r.ok ? r.json() : Promise.reject(r)))])
      .then(([c, catalogue]: [CatalogueValue[], StatusCatalogue]) => {
        setCategories(c);
        setVocabularies(catalogue.vocabularies);
      })
      .catch(() => !abort.signal.aborted && setPickersFailed(true));
    return () => abort.abort();
  }, []);

  const set = (key: FormField, value: string) => setValues((prev) => ({ ...prev, [key]: value }));

  function cancel() {
    if (dirty && !window.confirm(LEAVE_PROMPT)) return;
    onCancel();
  }

  function check(): boolean {
    const found: Partial<Record<FormField | "company", string>> = {};
    if (mode === "create" && !companyPick) found.company = "Choose the company";
    if (!values.title.trim()) found.title = "Job title is required";
    if (!values.location.trim()) found.location = "Job location is required";
    for (const key of ["experience_min_months", "experience_max_months"] as const) {
      if (Number.isNaN(monthsFromYears(values[key]))) found[key] = "Enter years as a number, for example 2 or 1.5";
    }
    const [min, max] = [monthsFromYears(values.experience_min_months), monthsFromYears(values.experience_max_months)];
    if (min != null && max != null && !Number.isNaN(min + max) && min > max) found.experience_max_months = "Must be at least the minimum experience";
    if (values.salary_min.trim() && values.salary_max.trim() && Number(values.salary_min) > Number(values.salary_max)) found.salary_max = "Must be at least the minimum salary";
    if (values.vacancies.trim() && !/^\d+$/.test(values.vacancies.trim())) found.vacancies = "Enter a whole number";
    setErrors(found);
    const first = (["company", ...FORM_FIELDS] as const).find((k) => found[k]);
    if (first) focus(`${idPrefix}-${first}`);
    return !first;
  }

  async function save() {
    if (busy || !check()) return;
    const body = requirementBody(values, mode === "edit" ? original.current : undefined);
    if (mode === "edit" && Object.keys(body).length === 0) return onSaved(requirement!, false);
    if (mode === "create") {
      body.company_id = companyPick!.id;
      if (recruiter) body.assigned_recruiter_user_id = recruiter;
    }
    setBusy(true);
    setFailure(null);
    try {
      const response = await fetch(mode === "create" ? REQUIREMENTS_URL : `${REQUIREMENTS_URL}/${requirement!.id}`, {
        method: mode === "create" ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => null);
      if (response.ok && isRequirementBody(data)) {
        onSaved(data.requirement, true);
        return;
      }
      const onFields = response.status === 422 ? fieldErrors(data?.detail) : null;
      if (onFields) {
        setErrors(onFields);
        focus(`${idPrefix}-${FORM_FIELDS.find((k) => onFields[k])}`);
      } else {
        setFailure(detailMessage(data?.detail, "Unable to save this requirement."));
        focus(`${idPrefix}-failure`);
      }
    } catch {
      setFailure(NOT_COMPLETED);
      focus(`${idPrefix}-failure`);
    } finally {
      setBusy(false);
    }
  }

  const describe = (key: string, hint?: string) => [errors[key as FormField] && `${idPrefix}-${key}-error`, hint && `${idPrefix}-${key}-hint`].filter(Boolean).join(" ") || undefined;
  const errorOf = (key: FormField | "company") =>
    errors[key] && (
      <p className="form-error" id={`${idPrefix}-${key}-error`}>
        {errors[key]}
      </p>
    );

  function textField(key: FormField) {
    const spec = TEXT[key]!;
    const common = {
      id: `${idPrefix}-${key}`,
      value: values[key],
      maxLength: spec.max,
      "aria-invalid": errors[key] ? true : undefined,
      "aria-describedby": describe(key, spec.hint),
      onChange: (e: { target: { value: string } }) => set(key, e.target.value),
    };
    const numeric = key === "vacancies" || key.startsWith("salary") || key.startsWith("experience");
    return (
      <div className="field" key={key}>
        <label htmlFor={common.id}>
          {spec.label}
          {spec.required && " (required)"}
        </label>
        {spec.multiline ? (
          <textarea {...common} rows={key === "description" ? 5 : 2} />
        ) : (
          <input {...common} type={spec.type === "date" ? "date" : "text"} inputMode={numeric ? "decimal" : undefined} autoComplete="off" required={spec.required} />
        )}
        {spec.hint && (
          <p className="muted field-help" id={`${idPrefix}-${key}-hint`}>
            {spec.hint}
          </p>
        )}
        {errorOf(key)}
      </div>
    );
  }

  function selectField(key: FormField, text: string, options: { id: string; name: string }[]) {
    return (
      <div className="field" key={key}>
        <label htmlFor={`${idPrefix}-${key}`}>{text}</label>
        <select id={`${idPrefix}-${key}`} value={values[key]} aria-invalid={errors[key] ? true : undefined} aria-describedby={describe(key)} onChange={(e) => set(key, e.target.value)}>
          <option value="">Not set</option>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>
        {errorOf(key)}
      </div>
    );
  }

  const vocabularyField = (key: FormField) => selectField(key, SELECTS[key]!.label, (vocabularies[SELECTS[key]!.vocabulary] ?? []).map((v) => ({ id: v, name: label(v) })));

  return (
    <form
      className="form"
      noValidate
      aria-busy={busy}
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        void save();
      }}
    >
      {pickersFailed && (
        <p className="form-error" role="alert">
          Some lists could not be loaded. Reload the page to choose a job category, work mode, shift, employment type or priority.
        </p>
      )}
      {mode === "create" && (
        <fieldset className="form-section">
          <legend>Company</legend>
          {company ? (
            <p style={{ margin: 0 }}>
              {company.label} {company.detail && <span className="muted">({company.detail})</span>}
            </p>
          ) : (
            <div className="field">
              <SearchableSelect id={`${idPrefix}-company`} label="Company (required)" noun="company" search={companySearch} onChange={setCompanyPick} />
              {errorOf("company")}
            </div>
          )}
          {canChooseRecruiter && (
            <div className="field">
              <SearchableSelect id={`${idPrefix}-recruiter`} label="Recruiter (optional)" noun="recruiter" search={searchRecruiters} onChange={(option) => setRecruiter(option?.id ?? null)} />
              <p className="muted field-help">Leave empty to give it to the company&apos;s recruiter.</p>
            </div>
          )}
        </fieldset>
      )}
      <fieldset className="form-section">
        <legend>Role</legend>
        <div className="form-grid">
          {textField("title")}
          {textField("department")}
          {selectField("job_category_id", "Job category", withCurrent(categories, requirement?.job_category))}
          {textField("vacancies")}
          {textField("qualification")}
          {textField("experience_min_months")}
          {textField("experience_max_months")}
          {textField("salary_min")}
          {textField("salary_max")}
        </div>
      </fieldset>
      <fieldset className="form-section">
        <legend>Work</legend>
        <div className="form-grid">
          {textField("location")}
          {vocabularyField("work_mode")}
          {vocabularyField("shift")}
          {vocabularyField("employment_type")}
          {textField("joining_requirement")}
          {textField("closes_on")}
          {textField("requirement_date")}
          {vocabularyField("priority")}
        </div>
      </fieldset>
      <fieldset className="form-section">
        <legend>Skills and description</legend>
        {textField("required_skills")}
        {textField("preferred_skills")}
        {textField("description")}
      </fieldset>
      {failure && (
        <p className="form-error" role="alert" id={`${idPrefix}-failure`} tabIndex={-1}>
          {failure}
        </p>
      )}
      <div className="actions">
        <button id={`${idPrefix}-save`} type="submit" className="btn small" disabled={busy}>
          {busy ? "Saving…" : mode === "create" ? "Save requirement" : "Save changes"}
        </button>
        <button type="button" className="btn secondary small" onClick={cancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}

"use client";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import StaleRecordNotice from "@/components/StaleRecordNotice";
import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import { activeValues, type CatalogueValue } from "@/lib/recruiterCatalogue";
import { recruiterSearch, type Ref } from "@/lib/recruiterCompanies";
import { contactsOf, isContactList } from "@/lib/recruiterContacts";
import {
  companySearch,
  FORM_FIELDS,
  type FormField,
  type FormValues,
  hiringManagerSearch,
  type InheritedTerm,
  isRequirementBody,
  label,
  monthsFromYears,
  DISCLOSURE_OPTIONS,
  ownerSearch,
  PAYMENT_TRIGGER_OPTIONS,
  type PossibleDuplicate,
  possibleDuplicate,
  type Requirement,
  requirementBody,
  REQUIREMENTS_PATH,
  REQUIREMENTS_URL,
  type StatusCatalogue,
  valuesOf,
  vendorSearch,
} from "@/lib/recruiterRequirements";
import { useStaleGuard } from "@/lib/staleGuard";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

// rec-007 (spec §6): add or edit a job requirement (EVID-018 §6; the company contact who gave it arrives with rec-004). Skills are typed
// one per comma or line and matched against the Skills Master on the server -- an unmatched one is kept and flagged on the detail page.
// The entry is never cleared on an error, and every rule is the server's; the checks here only save a round trip.
const LEAVE_PROMPT = "You have unsaved changes to this requirement. Leave without saving?";
type Text = { label: string; max: number; multiline?: boolean; type?: "date" | "number"; hint?: string; required?: boolean };
const TEXT: Partial<Record<FormField, Text>> = {
  requisition_reference: { label: "Requisition reference", max: 80, hint: "The client's own reference for this opening, if any" },
  title: { label: "Job title", max: 180, required: true },
  department: { label: "Department", max: 120 },
  vacancies: { label: "Number of vacancies", max: 5 },
  qualification: { label: "Qualification", max: 300 },
  experience_min_months: { label: "Experience from (years)", max: 5, hint: "For example 0 or 1.5" },
  experience_max_months: { label: "Experience to (years)", max: 5 },
  certifications: { label: "Certifications", max: 1000, multiline: true, hint: "One per line" },
  country: { label: "Country", max: 120 },
  state: { label: "State", max: 120 },
  city: { label: "City", max: 120 },
  travel_requirement: { label: "Travel", max: 120, hint: "For example Up to 25%" },
  salary_min: { label: "Salary from", max: 13 },
  salary_max: { label: "Salary to", max: 13 },
  salary_currency: { label: "Salary currency", max: 3, hint: "Three letters, for example INR or USD. Empty means INR." },
  benefits: { label: "Benefits", max: 1000, multiline: true, hint: "One per line" },
  expected_joining_date: { label: "Expected joining date", max: 10, type: "date" },
  location: { label: "Job location", max: 120, hint: "Work address or area. Leave empty to use the city, state and country." },
  joining_requirement: { label: "Joining requirement", max: 300, hint: "For example Immediate, or within 30 days" },
  closes_on: { label: "Application deadline", max: 10, type: "date" },
  requirement_date: { label: "Requirement date", max: 10, type: "date", hint: "The day the requirement was received. Today if left empty." },
  required_skills: { label: "Required skills", max: 3000, multiline: true, hint: "One per comma or line" },
  preferred_skills: { label: "Preferred skills", max: 3000, multiline: true, hint: "One per comma or line" },
  description: { label: "Job description", max: 10000, multiline: true },
  // pob-002 (DEC-SCOPE-407 R6/R7)
  interview_rounds: { label: "Interview rounds", max: 1300, multiline: true, hint: "One round per line, in order (at most 10)" },
  screening_steps: { label: "Screening steps", max: 1300, multiline: true, hint: "One step per line, in order (at most 10)" },
  expected_tat_days: { label: "Expected turnaround (days)", max: 3, hint: "The client's target from requirement to joining" },
  payment_days: { label: "Payment due (days after joining)", max: 3 },
  payment_terms: { label: "Payment terms", max: 2000, multiline: true },
  replacement_terms: { label: "Replacement terms", max: 2000, multiline: true },
  guarantee_days: { label: "Guarantee (days)", max: 3 }, // pob-025 G1
};
const NUMERIC = new Set<string>(["vacancies", "expected_tat_days", "payment_days", "guarantee_days"]);
const SELECTS: Partial<Record<FormField, { label: string; vocabulary: string }>> = {
  work_mode: { label: "Work mode", vocabulary: "work_mode" },
  shift: { label: "Shift", vocabulary: "shift" },
  employment_type: { label: "Employment type", vocabulary: "employment_type" },
  priority: { label: "Priority", vocabulary: "priority" },
};
// hrc-005: fixed choices the server owns too (relocation is a yes/no that may be left unstated; the pay period is hrc-011's)
const CHOICES: Partial<Record<FormField, { label: string; options: { id: string; name: string }[] }>> = {
  relocation_required: { label: "Relocation required", options: [{ id: "yes", name: "Yes" }, { id: "no", name: "No" }] },
  salary_period: { label: "Pay period", options: [{ id: "year", name: "A year" }, { id: "month", name: "A month" }] },
  payment_trigger: { label: "Payment trigger", options: PAYMENT_TRIGGER_OPTIONS }, // pob-002 R7
};
const SKILL_FIELDS = new Set<string>(["required_skills", "preferred_skills", "interview_rounds", "screening_steps"]); // a list's item error lands on the list
const FIELD_LABELS: Record<string, string> = {
  job_category_id: "Job category", skills: "Skills", status: "Status", assign: "Recruiter", weights: "Skill weights", lead_source_id: "Lead source",
  hiring_manager_user_id: "Hiring manager", decision_maker_contact_id: "Decision-maker", backup_owner_user_id: "Backup owner",
  via_vendor_id: "Via vendor", end_client_disclosure: "End client name", // pob-011
};

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

/** pob-002 R7: what an empty term falls back to. */
function inheritedHint(term: InheritedTerm | undefined): string {
  const fallback = term?.inherited ? term.value : null;
  return fallback ? `Leave empty to use the contract's: "${fallback.length > 120 ? `${fallback.slice(0, 120)}…` : fallback}"` : "Leave empty to use the contract's terms";
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
  onLatest,
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
  /** hrc-003: the latest requirement after a stale save was reloaded or reviewed, for the page behind the form. */
  onLatest?: (r: Requirement) => void;
}) {
  // hrc-003: the values and `updated_at` the form was opened with; a save refused as stale re-bases them (Reload / Review my changes).
  const guard = useStaleGuard<Requirement, FormValues>(requirement, valuesOf, (r) => r?.updated_at ?? null, onLatest);
  const { values, setValues, opened } = guard;
  const [companyPick, setCompanyPick] = useState<PickOption | null>(company ?? null);
  const [recruiter, setRecruiter] = useState<string | null>(null);
  const [errors, setErrors] = useState<Partial<Record<FormField | "company", string>>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [categories, setCategories] = useState<CatalogueValue[]>([]);
  const [sources, setSources] = useState<CatalogueValue[]>([]);
  // hrc-005 (V5): the server's possible duplicates, and the reason that saves anyway
  const [duplicate, setDuplicate] = useState<PossibleDuplicate | null>(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [vocabularies, setVocabularies] = useState<Record<string, string[]>>({});
  const [pickersFailed, setPickersFailed] = useState(false);
  // pob-002: the company's active contacts (the decision-maker) and the optional reason the save's revision records
  const [contacts, setContacts] = useState<{ id: string; name: string }[] | null>(null);
  const [revisionReason, setRevisionReason] = useState("");
  const terms = requirement?.commercial_terms;
  const showTerms = mode === "edit" && !!terms?.can_edit;
  const showBackup = mode === "edit" && !!requirement?.permissions.can_manage_owners;
  const companyId = requirement?.company.id ?? companyPick?.id ?? null;
  const searchBackups = useMemo(() => (requirement ? ownerSearch(requirement.id, "backup") : null), [requirement]);
  const focus = useFocusAfterRender();
  const idPrefix = mode === "create" ? "requirement-new" : `requirement-${requirement?.id}`;
  const dirty = FORM_FIELDS.some((k) => values[k] !== opened[k]) || recruiter !== null || (mode === "create" && !company && companyPick !== null);
  const searchRecruiters = useMemo(() => recruiterSearch(null), []);
  useLeaveGuard(dirty, LEAVE_PROMPT);

  useEffect(() => {
    const abort = new AbortController();
    Promise.all([
      activeValues("job-categories", abort.signal),
      activeValues("lead-sources", abort.signal),
      fetch(`${REQUIREMENTS_URL}/statuses`, { signal: abort.signal }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
    ])
      .then(([c, s, catalogue]: [CatalogueValue[], CatalogueValue[], StatusCatalogue]) => {
        setCategories(c);
        setSources(s);
        setVocabularies(catalogue.vocabularies);
      })
      .catch(() => !abort.signal.aborted && setPickersFailed(true));
    return () => abort.abort();
  }, []);

  useEffect(() => {
    if (!companyId) return setContacts([]);
    const abort = new AbortController();
    setContacts(null);
    fetch(contactsOf(companyId), { signal: abort.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setContacts(isContactList(data) ? data.items.filter((c) => c.active).map((c) => ({ id: c.id, name: c.designation ? `${c.name} (${c.designation})` : c.name })) : []))
      .catch(() => abort.signal.aborted || setContacts([]));
    return () => abort.abort();
  }, [companyId]);

  // The current decision-maker stays choosable even if since deactivated (the API keeps it; R6).
  const decisionMakers = useMemo(() => {
    const current = requirement?.decision_maker;
    const options = contacts ?? [];
    return current && !options.some((c) => c.id === current.id) ? [{ id: current.id, name: `${current.name}${current.active ? "" : " (inactive)"}` }, ...options] : options;
  }, [contacts, requirement?.decision_maker]);

  const set = (key: FormField, value: string) => setValues((prev) => ({ ...prev, [key]: value }));

  function cancel() {
    if (dirty && !window.confirm(LEAVE_PROMPT)) return;
    onCancel();
  }

  function check(): boolean {
    const found: Partial<Record<FormField | "company", string>> = {};
    if (mode === "create" && !companyPick) found.company = "Choose the company";
    if (!values.title.trim()) found.title = "Job title is required";
    if (![values.location, values.city, values.state, values.country].some((v) => v.trim())) found.location = "Enter the job location or its city";
    if (values.salary_currency.trim() && !/^[A-Za-z]{3}$/.test(values.salary_currency.trim())) found.salary_currency = "Enter three letters, for example INR or USD";
    for (const key of ["experience_min_months", "experience_max_months"] as const) {
      if (Number.isNaN(monthsFromYears(values[key]))) found[key] = "Enter years as a number, for example 2 or 1.5";
    }
    const [min, max] = [monthsFromYears(values.experience_min_months), monthsFromYears(values.experience_max_months)];
    if (min != null && max != null && !Number.isNaN(min + max) && min > max) found.experience_max_months = "Must be at least the minimum experience";
    if (values.salary_min.trim() && values.salary_max.trim() && Number(values.salary_min) > Number(values.salary_max)) found.salary_max = "Must be at least the minimum salary";
    for (const key of ["vacancies", "expected_tat_days", "payment_days", "guarantee_days"] as const) {
      if (values[key].trim() && !/^\d+$/.test(values[key].trim())) found[key] = "Enter a whole number";
    }
    // pob-002 R7: the days go with (and only with) "Days after joining"
    if (values.payment_trigger === "days_after_joining" && !values.payment_days.trim()) found.payment_days = "Enter the number of days after joining";
    setErrors(found);
    const first = (["company", ...FORM_FIELDS] as const).find((k) => found[k]);
    if (first) focus(`${idPrefix}-${first}`);
    return !first;
  }

  /** `anyway`: re-send after the possible-duplicate panel, with the user's reason (hrc-005 V5); a plain save re-checks from scratch. */
  async function save(anyway = false) {
    if (busy || !check()) return;
    if (anyway && !reason.trim()) {
      setReasonError("Give a reason to save anyway");
      focus(`${idPrefix}-duplicate-reason`);
      return;
    }
    if (!anyway) setDuplicate(null);
    const body = requirementBody(values, mode === "edit" ? opened : undefined);
    if (mode === "edit" && Object.keys(body).length === 0) return onSaved(requirement!, false);
    // pob-002 R7: a trigger other than "Days after joining" clears the stored days, so the pair stays valid
    if (values.payment_trigger !== "days_after_joining" && ("payment_trigger" in body || "payment_days" in body)) {
      if (opened.payment_days) body.payment_days = null;
      else delete body.payment_days; // the hidden field was typed in, then the trigger changed
    }
    if (mode === "edit") body.expected_updated_at = guard.token;
    if (mode === "edit" && revisionReason.trim()) body.revision_reason = revisionReason.trim();
    if (anyway) body.duplicate_reason = reason.trim();
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
      if (guard.caught({ ok: false, status: response.status, detail: data?.detail })) return;
      const duplicates = response.status === 409 ? possibleDuplicate(data?.detail) : null;
      if (duplicates) {
        setDuplicate(duplicates);
        setReasonError(null);
        focus(`${idPrefix}-duplicate`);
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

  function textField(key: FormField, hintOverride?: string) {
    const spec = { ...TEXT[key]!, ...(hintOverride ? { hint: hintOverride } : {}) };
    const common = {
      id: `${idPrefix}-${key}`,
      value: values[key],
      maxLength: spec.max,
      "aria-invalid": errors[key] ? true : undefined,
      "aria-describedby": describe(key, spec.hint),
      onChange: (e: { target: { value: string } }) => set(key, e.target.value),
    };
    const numeric = NUMERIC.has(key) || key.startsWith("salary") || key.startsWith("experience");
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

  function selectField(key: FormField, text: string, options: { id: string; name: string }[], blank = true) {
    return (
      <div className="field" key={key}>
        <label htmlFor={`${idPrefix}-${key}`}>{text}</label>
        <select id={`${idPrefix}-${key}`} value={values[key]} aria-invalid={errors[key] ? true : undefined} aria-describedby={describe(key)} onChange={(e) => set(key, e.target.value)}>
          {blank && <option value="">Not set</option>}
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
  const choiceField = (key: FormField) => selectField(key, CHOICES[key]!.label, CHOICES[key]!.options);

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
      {/* pob-011 (DEC-SCOPE-427 V2/V3): the company is the end client; a vendor may have passed the requirement on */}
      <fieldset className="form-section">
        <legend>Source</legend>
        <div className="form-grid">
          <div className="field">
            <SearchableSelect
              id={`${idPrefix}-via_vendor_id`}
              label="Via vendor (optional)"
              noun="company"
              search={vendorSearch}
              initial={requirement?.via_vendor ? { id: requirement.via_vendor.id, label: requirement.via_vendor.name, detail: requirement.via_vendor.code } : null}
              onChange={(option) => set("via_vendor_id", option?.id ?? "")}
            />
            <p className="muted field-help">When a staffing vendor passed this requirement on. The company stays the end client.</p>
            {errorOf("via_vendor_id")}
          </div>
          {selectField("end_client_disclosure", "End client name", DISCLOSURE_OPTIONS, false)}
        </div>
      </fieldset>
      <fieldset className="form-section">
        <legend>Identification</legend>
        <div className="form-grid">
          {textField("requisition_reference")}
          {selectField("lead_source_id", "Lead source", withCurrent(sources, requirement?.lead_source))}
        </div>
      </fieldset>
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
          {vocabularyField("employment_type")}
          {vocabularyField("shift")}
        </div>
        {textField("certifications")}
      </fieldset>
      <fieldset className="form-section">
        <legend>Location</legend>
        <div className="form-grid">
          {textField("country")}
          {textField("state")}
          {textField("city")}
          {textField("location")}
          {vocabularyField("work_mode")}
          {choiceField("relocation_required")}
          {textField("travel_requirement")}
        </div>
      </fieldset>
      <fieldset className="form-section">
        <legend>Compensation</legend>
        <div className="form-grid">
          {textField("salary_min")}
          {textField("salary_max")}
          {textField("salary_currency")}
          {choiceField("salary_period")}
        </div>
        {textField("benefits")}
      </fieldset>
      <fieldset className="form-section">
        <legend>Hiring plan</legend>
        <div className="form-grid">
          <div className="field">
            <SearchableSelect
              id={`${idPrefix}-hiring_manager_user_id`}
              label="Hiring manager"
              noun="manager"
              search={hiringManagerSearch}
              initial={requirement?.hiring_manager ? { id: requirement.hiring_manager.id, label: requirement.hiring_manager.full_name } : null}
              onChange={(option) => set("hiring_manager_user_id", option?.id ?? "")}
            />
            {errorOf("hiring_manager_user_id")}
          </div>
          {textField("joining_requirement")}
          {textField("expected_joining_date")}
          {textField("closes_on")}
          {textField("requirement_date")}
          {vocabularyField("priority")}
        </div>
      </fieldset>
      {/* pob-002 (DEC-SCOPE-407 R6): the client's hiring process */}
      <fieldset className="form-section">
        <legend>Hiring process</legend>
        <div className="form-grid">
          {textField("interview_rounds")}
          {textField("screening_steps")}
          {selectField("decision_maker_contact_id", contacts === null ? "Decision-maker (loading contacts…)" : "Decision-maker", decisionMakers)}
          {textField("expected_tat_days")}
        </div>
      </fieldset>
      {/* pob-002 R7: shown only to those who may change client terms; an empty term keeps the contract's */}
      {showTerms && (
        <fieldset className="form-section">
          <legend>Commercial terms</legend>
          <div className="form-grid">
            {choiceField("payment_trigger")}
            {values.payment_trigger === "days_after_joining" && textField("payment_days")}
            {textField("guarantee_days", terms?.guarantee_days?.inherited ? `Leave empty to use the contract's ${terms.guarantee_days.value} days` : "Leave empty to use the contract's guarantee")}
          </div>
          {textField("payment_terms", inheritedHint(terms?.payment_terms))}
          {textField("replacement_terms", inheritedHint(terms?.replacement_terms))}
        </fieldset>
      )}
      {/* pob-002 R9: the primary's owner rights, for an active recruiter */}
      {showBackup && searchBackups && (
        <fieldset className="form-section">
          <legend>Backup owner</legend>
          <div className="field">
            <SearchableSelect
              id={`${idPrefix}-backup_owner_user_id`}
              label="Backup owner"
              noun="recruiter"
              search={searchBackups}
              initial={requirement?.backup_owner ? { id: requirement.backup_owner.id, label: requirement.backup_owner.full_name } : null}
              onChange={(option) => set("backup_owner_user_id", option?.id ?? "")}
            />
            <p className="muted field-help">Has the same owner rights as the primary owner. Clear the choice to remove the backup.</p>
            {errorOf("backup_owner_user_id")}
          </div>
        </fieldset>
      )}
      <fieldset className="form-section">
        <legend>Skills and description</legend>
        {textField("required_skills")}
        {textField("preferred_skills")}
        {textField("description")}
      </fieldset>
      {mode === "edit" && (
        <div className="field">
          <label htmlFor={`${idPrefix}-revision-reason`}>Reason for this revision (optional)</label>
          <input id={`${idPrefix}-revision-reason`} type="text" maxLength={500} value={revisionReason} autoComplete="off" aria-describedby={`${idPrefix}-revision-reason-hint`}
            onChange={(e) => setRevisionReason(e.target.value)} />
          <p className="muted field-help" id={`${idPrefix}-revision-reason-hint`}>Saved with this revision, for example &quot;Client added a seat&quot;.</p>
        </div>
      )}
      <StaleRecordNotice
        guard={guard}
        labelOf={(key) => TEXT[key as FormField]?.label ?? SELECTS[key as FormField]?.label ?? CHOICES[key as FormField]?.label ?? FIELD_LABELS[key] ?? label(key)}
        display={(key, value) => {
          if (key === "job_category_id") return withCurrent(categories, requirement?.job_category).find((c) => c.id === value)?.name ?? value;
          if (key === "lead_source_id") return withCurrent(sources, requirement?.lead_source).find((c) => c.id === value)?.name ?? value;
          if (key === "decision_maker_contact_id") return decisionMakers.find((c) => c.id === value)?.name ?? value;
          if (CHOICES[key as FormField]) return CHOICES[key as FormField]!.options.find((o) => o.id === value)?.name ?? value;
          return SELECTS[key as FormField] && value ? label(value) : value;
        }}
        onReload={guard.reload}
        onReview={guard.reviewMine}
      />
      {duplicate && (
        <section className="action-card wide" id={`${idPrefix}-duplicate`} tabIndex={-1} aria-labelledby={`${idPrefix}-duplicate-title`}>
          <h4 id={`${idPrefix}-duplicate-title`} style={{ margin: 0 }}>
            Possible duplicate
          </h4>
          <p role="alert" style={{ margin: 0 }}>
            {duplicate.message}. Check {duplicate.total === 1 ? "it" : `these ${duplicate.total}`} before saving.
          </p>
          <ul style={{ margin: 0, paddingLeft: 18, overflowWrap: "anywhere" }}>
            {duplicate.matches.map((m) => (
              <li key={m.id}>
                <a href={`${REQUIREMENTS_PATH}/${m.id}`} target="_blank" rel="noreferrer">
                  {m.code} (opens in a new tab)
                </a>{" "}
                {m.title} · {m.location} · {m.status_label}
                {m.requisition_reference && <> · Ref {m.requisition_reference}</>}
              </li>
            ))}
          </ul>
          <div className="field">
            <label htmlFor={`${idPrefix}-duplicate-reason`}>Why is this not a duplicate? (required to save anyway)</label>
            <textarea
              id={`${idPrefix}-duplicate-reason`}
              rows={2}
              maxLength={500}
              value={reason}
              aria-invalid={reasonError ? true : undefined}
              aria-describedby={reasonError ? `${idPrefix}-duplicate-reason-error` : undefined}
              onChange={(e) => setReason(e.target.value)}
            />
            {reasonError && (
              <p className="form-error" id={`${idPrefix}-duplicate-reason-error`}>
                {reasonError}
              </p>
            )}
          </div>
          <div className="actions">
            <button type="button" className="btn small" disabled={busy} onClick={() => void save(true)}>
              {busy ? "Saving…" : "Save anyway"}
            </button>
            <button type="button" className="btn secondary small" disabled={busy} onClick={() => { setDuplicate(null); focus(`${idPrefix}-save`); }}>
              Go back
            </button>
          </div>
        </section>
      )}
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

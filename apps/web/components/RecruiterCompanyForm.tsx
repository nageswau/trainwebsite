"use client";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { plural } from "@/lib/plural";
import { activeValues, CAMPAIGNS_URL, type CatalogueValue, type RecCampaign } from "@/lib/recruiterCatalogue";
import {
  bdmSearch,
  type Company,
  companyBody,
  COMPANIES_URL,
  type Duplicate,
  duplicateOf,
  type FormField,
  isCompanyBody,
  PICK_FIELDS,
  PRIORITIES,
  PRIORITY_LABEL,
  recruiterSearch,
  type Ref,
  TEXT_FIELDS,
  valuesOf,
} from "@/lib/recruiterCompanies";
import { readAll } from "@/lib/telecallerCatalogue";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

// rec-003 (spec §6): add or edit a company (EVID-018 §2/§3, the company side; contacts arrive with rec-004). A likely duplicate is the
// server's 409; the user decides, and "Save anyway" resends the same entry with confirm_duplicate (the BdmOrganizationForm pattern). The
// entry is never cleared on an error, and every rule is the server's -- the checks here only save a round trip.
const LEAVE_PROMPT = "You have unsaved changes to this company. Leave without saving?";
const ALL_FIELDS: FormField[] = [...TEXT_FIELDS, ...PICK_FIELDS];
type Text = { label: string; max: number; multiline?: boolean; type?: string; hint?: string };
const TEXT: Record<(typeof TEXT_FIELDS)[number], Text> = {
  name: { label: "Company name", max: 180 },
  website: { label: "Website", max: 300, type: "url", hint: "For example abc.com" },
  linkedin_url: { label: "LinkedIn", max: 300, type: "url", hint: "The company page link" },
  city: { label: "City", max: 120 },
  state: { label: "State", max: 120 },
  country: { label: "Country", max: 120 },
  head_office: { label: "Head office", max: 300 },
  branches: { label: "Branches", max: 1000, multiline: true, hint: "One per line" },
  description: { label: "Company description", max: 2000, multiline: true },
  employee_count: { label: "Number of employees", max: 9 },
};

/** FastAPI's 422 list -> errors at the form's fields; null when any item is about something else (then one message shows it all). */
function fieldErrors(detail: unknown): Partial<Record<FormField, string>> | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const found: Partial<Record<FormField, string>> = {};
  for (const item of detail as { loc?: unknown[] }[]) {
    const [where, field] = item?.loc ?? [];
    if (where !== "body" || item.loc!.length !== 2 || !ALL_FIELDS.includes(field as FormField)) return null;
    found[field as FormField] = detailMessage([item]);
  }
  return found;
}

/** A picker's options: the active values plus the stored one when it has since been deactivated (keeping it stays allowed). */
function withCurrent(options: { id: string; name: string }[], current: Ref | null | undefined) {
  return current && !options.some((o) => o.id === current.id) ? [...options, { id: current.id, name: `${current.name} (inactive)` }] : options;
}

export default function RecruiterCompanyForm({
  mode,
  company,
  canChooseRecruiter,
  onSaved,
  onCancel,
}: {
  mode: "create" | "edit";
  company?: Company;
  /** Managers and super admin may hand a new company to a recruiter (else it is unassigned); a recruiter's is always their own. */
  canChooseRecruiter: boolean;
  /** `saved` is false when there was nothing to change. */
  onSaved: (c: Company, saved: boolean) => void;
  onCancel: () => void;
}) {
  const original = useRef(valuesOf(company));
  const [values, setValues] = useState(original.current);
  const [recruiter, setRecruiter] = useState<string | null>(null);
  const [errors, setErrors] = useState<Partial<Record<FormField, string>>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<Duplicate | null>(null);
  const [busy, setBusy] = useState(false);
  const [industries, setIndustries] = useState<CatalogueValue[]>([]);
  const [sizes, setSizes] = useState<CatalogueValue[]>([]);
  const [sources, setSources] = useState<CatalogueValue[]>([]);
  const [campaigns, setCampaigns] = useState<RecCampaign[]>([]);
  const [pickersFailed, setPickersFailed] = useState(false);
  const focus = useFocusAfterRender();
  const idPrefix = mode === "create" ? "company-new" : `company-${company?.id}`;
  const dirty = ALL_FIELDS.some((k) => values[k] !== original.current[k]) || recruiter !== null;
  const searchRecruiters = useMemo(() => recruiterSearch(null), []);
  useLeaveGuard(dirty, LEAVE_PROMPT);

  useEffect(() => {
    const abort = new AbortController();
    Promise.all([activeValues("industries", abort.signal), activeValues("company-sizes", abort.signal), activeValues("lead-sources", abort.signal), readAll<RecCampaign>(CAMPAIGNS_URL, abort.signal)])
      .then(([i, z, s, c]) => {
        setIndustries(i);
        setSizes(z);
        setSources(s);
        setCampaigns(c);
      })
      .catch(() => !abort.signal.aborted && setPickersFailed(true));
    return () => abort.abort();
  }, []);

  const set = (key: FormField, value: string) => setValues((prev) => ({ ...prev, [key]: value }));
  // A campaign belongs to one lead source: choosing one fills its source; changing the source drops a campaign of another source.
  const pickCampaign = (id: string) => {
    const source = campaigns.find((c) => c.id === id)?.lead_source.id;
    setValues((prev) => ({ ...prev, campaign_id: id, lead_source_id: source ?? prev.lead_source_id }));
  };
  const pickSource = (id: string) => {
    setValues((prev) => {
      const keep = campaigns.find((c) => c.id === prev.campaign_id)?.lead_source.id === id;
      return { ...prev, lead_source_id: id, campaign_id: keep ? prev.campaign_id : "" };
    });
  };
  const campaignOptions = campaigns.filter((c) => !values.lead_source_id || c.lead_source.id === values.lead_source_id);

  function cancel() {
    if (dirty && !window.confirm(LEAVE_PROMPT)) return;
    onCancel();
  }

  function check(): boolean {
    const found: Partial<Record<FormField, string>> = {};
    if (!values.name.trim()) found.name = "Company name is required";
    const count = values.employee_count.trim();
    if (count && !/^\d+$/.test(count)) found.employee_count = "Number of employees must be a whole number";
    setErrors(found);
    const first = ALL_FIELDS.find((k) => found[k]);
    if (first) focus(`${idPrefix}-${first}`);
    return !first;
  }

  async function save(confirm = false) {
    if (busy || !check()) return;
    const body = companyBody(values, mode === "edit" ? original.current : undefined);
    if (mode === "edit" && Object.keys(body).length === 0) return onSaved(company!, false);
    if (mode === "create" && recruiter) body.assigned_recruiter_user_id = recruiter;
    setBusy(true);
    setFailure(null);
    try {
      const response = await fetch(mode === "create" ? COMPANIES_URL : `${COMPANIES_URL}/${company!.id}`, {
        method: mode === "create" ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(confirm ? { ...body, confirm_duplicate: true } : body),
      });
      const data = await response.json().catch(() => null);
      if (response.ok && isCompanyBody(data)) {
        setDuplicate(null);
        onSaved(data.company, true);
        return;
      }
      const dup = response.status === 409 ? duplicateOf(data?.detail) : null;
      const onFields = response.status === 422 ? fieldErrors(data?.detail) : null;
      if (dup) {
        setDuplicate(dup);
        focus(`${idPrefix}-duplicate`);
      } else if (onFields) {
        setErrors(onFields);
        focus(`${idPrefix}-${ALL_FIELDS.find((k) => onFields[k])}`);
      } else {
        setFailure(detailMessage(data?.detail, "Unable to save this company."));
        focus(`${idPrefix}-failure`);
      }
    } catch {
      setFailure(NOT_COMPLETED);
      focus(`${idPrefix}-failure`);
    } finally {
      setBusy(false);
    }
  }

  const describe = (key: FormField, hint?: string) => [errors[key] && `${idPrefix}-${key}-error`, hint && `${idPrefix}-${key}-hint`].filter(Boolean).join(" ") || undefined;
  const errorOf = (key: FormField) =>
    errors[key] && (
      <p className="form-error" id={`${idPrefix}-${key}-error`}>
        {errors[key]}
      </p>
    );

  function textField(key: (typeof TEXT_FIELDS)[number]) {
    const spec = TEXT[key];
    const common = {
      id: `${idPrefix}-${key}`,
      value: values[key],
      maxLength: spec.max,
      "aria-invalid": errors[key] ? true : undefined,
      "aria-describedby": describe(key, spec.hint),
      onChange: (e: { target: { value: string } }) => set(key, e.target.value),
    };
    return (
      <div className="field" key={key}>
        <label htmlFor={common.id}>
          {spec.label}
          {key === "name" && " (required)"}
        </label>
        {spec.multiline ? (
          <textarea {...common} rows={3} />
        ) : (
          <input {...common} type="text" inputMode={key === "employee_count" ? "numeric" : spec.type === "url" ? "url" : undefined} autoComplete="off" required={key === "name"} />
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

  function selectField(key: FormField, label: string, options: { id: string; name: string }[], onChange = (v: string) => set(key, v)) {
    return (
      <div className="field" key={key}>
        <label htmlFor={`${idPrefix}-${key}`}>{label}</label>
        <select id={`${idPrefix}-${key}`} value={values[key]} aria-invalid={errors[key] ? true : undefined} aria-describedby={describe(key)} onChange={(e) => onChange(e.target.value)}>
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
          Some lists could not be loaded. Reload the page to choose an industry, size, lead source or campaign.
        </p>
      )}
      <fieldset className="form-section">
        <legend>Company details</legend>
        <div className="form-grid">
          {textField("name")}
          {textField("website")}
          {textField("linkedin_url")}
          {selectField("industry_id", "Industry", withCurrent(industries, company?.industry))}
          {selectField("company_size_id", "Company size", withCurrent(sizes, company?.company_size))}
          {textField("employee_count")}
          {textField("city")}
          {textField("state")}
          {textField("country")}
          {textField("head_office")}
        </div>
        {textField("branches")}
        {textField("description")}
      </fieldset>
      <fieldset className="form-section">
        <legend>Lead</legend>
        <div className="form-grid">
          {selectField("lead_source_id", "Lead source", withCurrent(sources, company?.lead_source), pickSource)}
          {selectField("campaign_id", "Campaign", withCurrent(campaignOptions.map((c) => ({ id: c.id, name: c.name })), company?.campaign), pickCampaign)}
          {selectField("priority", "Priority", PRIORITIES.map((p) => ({ id: p, name: PRIORITY_LABEL[p] })))}
          <div className="field">
            <SearchableSelect
              id={`${idPrefix}-assigned_bdm_user_id`}
              label="Assigned BDM"
              noun="BDM"
              search={bdmSearch}
              initial={company?.assigned_bdm ? { id: company.assigned_bdm.id, label: company.assigned_bdm.full_name } : null}
              onChange={(option) => set("assigned_bdm_user_id", option?.id ?? "")}
            />
            {errorOf("assigned_bdm_user_id")}
          </div>
          {mode === "create" && canChooseRecruiter && (
            <div className="field">
              <SearchableSelect id={`${idPrefix}-recruiter`} label="Recruiter (optional)" noun="recruiter" search={searchRecruiters} onChange={(option) => setRecruiter(option?.id ?? null)} />
              <p className="muted field-help">
                Leave empty to put the company in the unassigned queue.
              </p>
            </div>
          )}
        </div>
      </fieldset>
      {duplicate && (
        <div role="alert" className="form-error">
          <h4 id={`${idPrefix}-duplicate`} tabIndex={-1} style={{ margin: "0 0 8px" }}>
            {duplicate.message}
          </h4>
          <ul>
            {duplicate.matches.map((m) => (
              <li key={m.id}>
                {m.code} — {m.name}
                {m.city ? `, ${m.city}` : ""}
                {m.archived ? " · Archived" : ""}
              </li>
            ))}
          </ul>
          {duplicate.total > duplicate.matches.length && <p>{plural(duplicate.total - duplicate.matches.length, "more similar company", "more similar companies")}.</p>}
          <button type="button" className="btn small" onClick={() => void save(true)} disabled={busy}>
            Save anyway
          </button>{" "}
          <button
            type="button"
            className="btn secondary small"
            onClick={() => {
              setDuplicate(null);
              focus(`${idPrefix}-save`);
            }}
          >
            Go back
          </button>
        </div>
      )}
      {failure && (
        <p className="form-error" role="alert" id={`${idPrefix}-failure`} tabIndex={-1}>
          {failure}
        </p>
      )}
      <div className="actions">
        <button id={`${idPrefix}-save`} type="submit" className="btn small" disabled={busy || duplicate !== null}>
          {busy ? "Saving…" : mode === "create" ? "Save company" : "Save changes"}
        </button>
        <button type="button" className="btn secondary small" onClick={cancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}

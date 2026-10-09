"use client";
import { type FormEvent, type ReactNode, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import { countrySearch } from "@/lib/universities";
import { type Agreement, type AgreementOptions, AGREEMENT_TYPES, agreementsUrl, agreementUrl, EXCLUSIVITY, signatorySearch } from "@/lib/universityAgreements";

// upc-014 (§13): one form for a new agreement (a draft) and for editing one. The API decides what may change (AG11): `canTerms` opens the
// terms, `canSigning` the document and both signatories. An edit sends only the fields that changed. Texts are data only.
type Values = Record<string, string>;
const TEXTS = ["commercial_terms", "recruitment_rights", "payment_terms", "marketing_rights"] as const;
const TEXT_LABELS: Record<(typeof TEXTS)[number], string> = {
  commercial_terms: "Commercial terms (summary)", recruitment_rights: "Student recruitment rights", payment_terms: "Payment terms", marketing_rights: "Marketing rights",
};
const SAVE_FAILED = "The agreement could not be saved. Try again.";

function startValues(a: Agreement | null): Values {
  const pick = (v: string | null | undefined) => v ?? "";
  return {
    agreement_type: a?.agreement_type ?? "", start_date: pick(a?.start_date), expiry_date: pick(a?.expiry_date), renewal_date: pick(a?.renewal_date),
    exclusivity: a?.exclusivity ?? "", territory: pick(a?.territory), commercial_terms: pick(a?.commercial_terms), recruitment_rights: pick(a?.recruitment_rights),
    payment_terms: pick(a?.payment_terms), marketing_rights: pick(a?.marketing_rights), document_id: pick(a?.document?.id),
    edusphere_signatory_user_id: pick(a?.edusphere_signatory?.id), edusphere_signed_on: pick(a?.edusphere_signed_on),
    university_signatory_name: pick(a?.university_signatory_name), university_signed_on: pick(a?.university_signed_on),
  };
}

const sameIds = (a: string[], b: string[]) => a.length === b.length && a.every((id) => b.includes(id));
const today = () => new Date().toLocaleDateString("en-CA"); // yyyy-mm-dd in the browser's zone

export default function AgreementForm({ universityId, options, agreement = null, canTerms = true, canSigning = true, onSaved, onCancel }: {
  universityId: string; options: AgreementOptions; agreement?: Agreement | null; canTerms?: boolean; canSigning?: boolean;
  onSaved: (message: string) => void; onCancel: () => void;
}) {
  const [values, setValues] = useState<Values>(() => startValues(agreement));
  const [allCourses, setAllCourses] = useState(agreement?.all_courses ?? false);
  const [courseIds, setCourseIds] = useState<string[]>(() => agreement?.courses.map((c) => c.id) ?? []);
  const [countries, setCountries] = useState<PickOption[]>(() => agreement?.countries.map((c) => ({ id: c.id, label: c.name })) ?? []);
  const [pickerKey, setPickerKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const prefix = agreement ? `ag-${agreement.id}` : "ag-new";
  const set = (key: string) => (e: { target: { value: string } }) => setValues((v) => ({ ...v, [key]: e.target.value }));
  const type = values.agreement_type;
  const documents = options.documents.filter((d) => d.kind === type);

  function body(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    const start = startValues(agreement);
    const keys = [...(canTerms ? ["start_date", "expiry_date", "renewal_date", "exclusivity", "territory", ...TEXTS] : []),
      ...(canSigning ? ["document_id", "edusphere_signatory_user_id", "edusphere_signed_on", "university_signatory_name", "university_signed_on"] : [])];
    if (!agreement) keys.unshift("agreement_type");
    for (const key of keys) {
      const value = values[key].trim() || null; // blank = no value (an edit sends null to clear it)
      if (agreement ? value !== (start[key] || null) : value !== null) out[key] = value;
    }
    if (canTerms) {
      const ids = allCourses ? [] : courseIds;
      if (!agreement || allCourses !== agreement.all_courses) out.all_courses = allCourses;
      if (!agreement || !sameIds(ids, agreement.courses.map((c) => c.id))) out.course_ids = ids;
      const chosen = countries.map((c) => c.id);
      if (!agreement || !sameIds(chosen, agreement.countries.map((c) => c.id))) out.country_ids = chosen;
    }
    return out;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!agreement && !type) return setError("Choose the agreement type.");
    if (canTerms && (!values.start_date || !values.expiry_date)) return setError("Enter the start and expiry dates.");
    if (canTerms && values.expiry_date <= values.start_date) return setError("The expiry date must be after the start date.");
    if (!agreement && !values.exclusivity) return setError("Choose exclusive or non-exclusive.");
    const payload = body();
    if (agreement && Object.keys(payload).length === 0) return onSaved("No changes to save.");
    setError(null);
    setBusy(true);
    const outcome = agreement ? await sendJson(agreementUrl(agreement.id), "PATCH", payload) : await sendJson(agreementsUrl(universityId), "POST", payload);
    setBusy(false);
    if (outcome.ok) {
      const saved = outcome.data.agreement as Agreement | undefined;
      return onSaved(agreement ? "Agreement updated." : `Agreement ${saved?.mou_number} created as a draft.`);
    }
    setError(outcome.status !== undefined && outcome.detail === undefined ? SAVE_FAILED : outcome.message);
  }

  const field = (key: string, label: string, input: ReactNode) => (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor={`${prefix}-${key}`}>{label}</label>
      {input}
    </div>
  );
  const date = (key: string, label: string, extra: { max?: string; disabled?: boolean } = {}) =>
    field(key, label, <input id={`${prefix}-${key}`} type="date" value={values[key]} onChange={set(key)} max={extra.max} disabled={busy || extra.disabled} />);
  const grid = { display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" } as const;

  return (
    <form onSubmit={submit} aria-label={agreement ? `Edit ${agreement.mou_number}` : "New agreement"} aria-busy={busy} style={{ display: "grid", gap: 12 }}>
      {canTerms && (
        <fieldset className="card" style={{ padding: 14, display: "grid", gap: 12 }} disabled={busy}>
          <legend>Terms</legend>
          <div style={grid}>
            {agreement
              ? field("agreement_type", "Agreement type", <input id={`${prefix}-agreement_type`} value={AGREEMENT_TYPES[type] ?? type} readOnly />)
              : field("agreement_type", "Agreement type (required)", (
                <select id={`${prefix}-agreement_type`} value={type} onChange={(e) => setValues((v) => ({ ...v, agreement_type: e.target.value, document_id: "" }))} autoFocus>
                  <option value="">Choose a type</option>
                  {Object.entries(AGREEMENT_TYPES).map(([key, word]) => <option key={key} value={key}>{word}</option>)}
                </select>
              ))}
            {field("exclusivity", "Exclusivity (required)", (
              <select id={`${prefix}-exclusivity`} value={values.exclusivity} onChange={set("exclusivity")}>
                {!agreement && <option value="">Choose</option>}
                {Object.entries(EXCLUSIVITY).map(([key, word]) => <option key={key} value={key}>{word}</option>)}
              </select>
            ))}
            {date("start_date", "Start date (required)")}
            {date("expiry_date", "Expiry date (required)")}
            {date("renewal_date", "Renewal date")}
          </div>
          {field("territory", "Territory", <input id={`${prefix}-territory`} value={values.territory} maxLength={500} onChange={set("territory")} placeholder="India (all states)" />)}
          <div style={grid}>
            {TEXTS.map((key) => (
              <div key={key}>{field(key, TEXT_LABELS[key], <textarea id={`${prefix}-${key}`} rows={3} maxLength={2000} value={values[key]} onChange={set(key)} />)}</div>
            ))}
          </div>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>Commission is recorded separately, in the restricted commercial terms.</p>
          <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 6 }}>
            <legend style={{ fontWeight: 700 }}>Courses covered</legend>
            <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <input type="checkbox" checked={allCourses} onChange={(e) => setAllCourses(e.target.checked)} /> All courses of this university
            </label>
            {!allCourses && (options.courses.length === 0 ? <p className="muted" style={{ margin: 0 }}>No courses are recorded for this university yet.</p> : (
              <ul className="list-clean" style={{ display: "grid", gap: 4, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
                {options.courses.map((c) => (
                  <li key={c.id}>
                    <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                      <input type="checkbox" checked={courseIds.includes(c.id)}
                        onChange={(e) => setCourseIds((ids) => (e.target.checked ? [...ids, c.id] : ids.filter((id) => id !== c.id)))} />
                      {c.title} <span className="muted">({c.level})</span>
                    </label>
                  </li>
                ))}
              </ul>
            ))}
          </fieldset>
          <div style={{ display: "grid", gap: 8 }}>
            <strong>Countries covered</strong>
            {countries.length > 0 && (
              <ul aria-label="Countries covered" style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexWrap: "wrap", gap: 8 }}>
                {countries.map((c) => (
                  <li key={c.id} className="badge" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    {c.label}
                    <button type="button" className="btn ghost small" aria-label={`Remove ${c.label}`} disabled={busy} onClick={() => setCountries((list) => list.filter((x) => x.id !== c.id))}>×</button>
                  </li>
                ))}
              </ul>
            )}
            <SearchableSelect key={pickerKey} id={`${prefix}-country`} label="Add a country" noun="country" search={countrySearch} disabled={busy}
              onChange={(option) => {
                if (option && !countries.some((c) => c.id === option.id)) setCountries((list) => [...list, option]);
                if (option) setPickerKey((k) => k + 1);
              }} />
          </div>
        </fieldset>
      )}
      {canSigning && (
        <fieldset className="card" style={{ padding: 14, display: "grid", gap: 12 }} disabled={busy}>
          <legend>Signing</legend>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>Needed to mark the agreement Signed: the agreement document and both signatories with their dates.</p>
          <div style={grid}>
            {field("document_id", "Agreement document", (
              <select id={`${prefix}-document_id`} value={values.document_id} onChange={set("document_id")} disabled={busy || !type} aria-describedby={`${prefix}-document_id-hint`}>
                <option value="">None yet</option>
                {documents.map((d) => <option key={d.id} value={d.id}>{d.title} (version {d.current_version})</option>)}
              </select>
            ))}
            <div className="field" style={{ margin: 0 }}>
              <SearchableSelect id={`${prefix}-edusphere_signatory_user_id`} label="Signed by EduSphere" noun="employee" search={signatorySearch} disabled={busy}
                initial={agreement?.edusphere_signatory ? { id: agreement.edusphere_signatory.id, label: agreement.edusphere_signatory.full_name } : null}
                onChange={(option) => setValues((v) => ({ ...v, edusphere_signatory_user_id: option?.id ?? "" }))} />
            </div>
            {date("edusphere_signed_on", "EduSphere signed on", { max: today() })}
            {field("university_signatory_name", "Signed by the university (name)", (
              <input id={`${prefix}-university_signatory_name`} value={values.university_signatory_name} maxLength={200} onChange={set("university_signatory_name")} />
            ))}
            {date("university_signed_on", "University signed on", { max: today() })}
          </div>
          <p className="muted" id={`${prefix}-document_id-hint`} style={{ margin: 0, fontSize: 13 }}>
            {type ? `Upload the ${AGREEMENT_TYPES[type] ?? type} in the Documents section first; documents of that kind are listed here.` : "Choose the agreement type first."}
          </p>
        </fieldset>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : agreement ? "Save changes" : "Create draft"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}

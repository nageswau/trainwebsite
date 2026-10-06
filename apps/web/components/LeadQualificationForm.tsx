"use client";

import { type FormEvent, useEffect, useId, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmTravel";
import { formatDate } from "@/lib/formatDate";
import { useLeaveGuard } from "@/lib/useLeaveGuard";
import { BASIC_FIELDS, REQUIREMENT, qualificationUrl, type LeadQualification, type QualField, type QualKey } from "@/lib/telecallerLeads";

type Draft = Partial<Record<QualKey, string>>;
type Loaded = { productId: string | null; data: LeadQualification | "failed" } | null;

// QD2: the fieldsets that apply to the lead's product group -- basic always, plus the IT or overseas requirement.
const sections = (q: LeadQualification) => {
  const group = q.product_group === "it" || q.product_group === "overseas" ? REQUIREMENT[q.product_group] : null;
  // `product` labels the lead's product (QF1: shown, changed in Lead details) -- "Course interested in" or "Destination"
  return [{ legend: "Basic qualification", fields: BASIC_FIELDS, product: null as string | null }, ...(group ? [group] : [])];
};
const applicable = (q: LeadQualification) => sections(q).flatMap((s) => s.fields);
const draftOf = (q: LeadQualification): Draft => Object.fromEntries(applicable(q).map((f) => [f.key, q[f.key] === null ? "" : String(q[f.key])]));
const shown = (field: QualField, value: string | number | null) =>
  value === null || value === "" ? null : field.kind === "select" || field.kind === "radio" ? field.options.find((o) => o.value === value)?.label ?? value : value;

function ProductNote({ q }: { q: LeadQualification }) {
  if (!q.product) return <p className="muted" style={{ margin: 0, fontSize: 13 }}>Set the lead&apos;s product interest in Lead details to see its IT or overseas questions.</p>;
  if (q.product_group === "other") return <p className="muted" style={{ margin: 0, fontSize: 13 }}>{q.product.name} has no IT or overseas questions.</p>;
  return null;
}

/** tel-009 (spec §4; AC1-AC4; QF1, QD1-QD2): the lead's qualification -- read on open and again whenever the lead's product changes (the
 *  section follows the saved product; the other group's values stay stored, hidden). A read-only lead shows the view only. A save
 *  hands the result back, so the panel's Lead details show the shared answers (qualification, passing year, city, state). */
export default function LeadQualificationForm({ leadId, productId, readOnly, onSaved }: {
  leadId: string; productId: string | null; readOnly: boolean; onSaved: (q: LeadQualification) => void;
}) {
  const idp = useId();
  const [loaded, setLoaded] = useState<Loaded>(null);
  const [attempt, setAttempt] = useState(0);
  const [draft, setDraft] = useState<Draft | null>(null); // null = viewing
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch(qualificationUrl(leadId), { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Request failed (${response.status})`);
        setLoaded({ productId, data: (await response.json()) as LeadQualification });
      })
      .catch(() => controller.signal.aborted || setLoaded({ productId, data: "failed" }));
    setDraft(null); // a product change while editing re-lays the form from the saved product
    return () => controller.abort();
  }, [leadId, productId, attempt]);

  const q = loaded && loaded.productId === productId && loaded.data !== "failed" ? loaded.data : null;
  useLeaveGuard(!!q && !!draft && JSON.stringify(draft) !== JSON.stringify(draftOf(q)) && !busy, "Discard the qualification changes?");

  const fieldId = (key: string) => `${idp}-${key}`;
  const errorId = (key: string) => `${idp}-${key}-error`;
  const set = (key: QualKey, value: string) => {
    setDraft((d) => ({ ...d, [key]: value }));
    setSaved(false);
  };

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!q || !draft) return;
    const body: Record<string, string | number | null> = {};
    const local: Record<string, string> = {};
    for (const field of applicable(q)) {
      const text = (draft[field.key] ?? "").trim();
      if (field.kind !== "number") body[field.key] = text || null;
      else if (!text) body[field.key] = null;
      else {
        const value = Number(text);
        const whole = field.step === 1 ? Number.isInteger(value) : Math.round(value * 100) === value * 100;
        if (!Number.isFinite(value) || !whole || value < field.min || value > field.max) local[field.key] = field.error;
        body[field.key] = value;
      }
    }
    setErrors(local);
    if (Object.keys(local).length) return setFailure("Check the highlighted fields.");
    setBusy(true);
    const outcome = await sendJson(qualificationUrl(leadId), "PUT", body);
    setBusy(false);
    if (!outcome.ok) {
      const mapped = fieldErrors(outcome.detail);
      setErrors(mapped);
      return setFailure(Object.keys(mapped).length ? "Check the highlighted fields." : outcome.message);
    }
    const next = outcome.data as unknown as LeadQualification;
    setLoaded({ productId, data: next });
    setDraft(null);
    setFailure(null);
    setSaved(true);
    onSaved(next);
  }

  function control(field: QualField) {
    const value = draft?.[field.key] ?? "";
    const invalid = errors[field.key] ? { "aria-invalid": true as const, "aria-describedby": errorId(field.key) } : {};
    const error = errors[field.key] && <p id={errorId(field.key)} className="form-error" style={{ margin: 0 }}>{errors[field.key]}</p>;
    if (field.kind === "radio") {
      return (
        <fieldset className="field" key={field.key} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }} {...invalid}>
          <legend style={{ fontWeight: 600, padding: 0 }}>{field.label}</legend>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 4 }}>
            {field.options.map((o) => (
              <label key={o.value} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input type="radio" name={fieldId(field.key)} value={o.value} checked={value === o.value} disabled={busy} onChange={() => set(field.key, o.value)} />
                {o.label}
              </label>
            ))}
            {value && <button type="button" className="btn secondary small" disabled={busy} onClick={() => set(field.key, "")}>Clear</button>}
          </div>
          {error}
        </fieldset>
      );
    }
    return (
      <div className="field" key={field.key}>
        <label htmlFor={fieldId(field.key)}>{field.label}</label>
        {field.kind === "select" ? (
          <select id={fieldId(field.key)} value={value} disabled={busy} onChange={(e) => set(field.key, e.target.value)} {...invalid}>
            <option value="">Not recorded</option>
            {field.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        ) : (
          <input id={fieldId(field.key)} value={value} disabled={busy} onChange={(e) => set(field.key, e.target.value)} {...invalid}
            {...(field.kind === "number" ? { type: "number", min: field.min, max: field.max, step: field.step, inputMode: field.step === 1 ? "numeric" : "decimal" as const }
              : field.kind === "text" ? { maxLength: field.max } : {})} />
        )}
        {error}
      </div>
    );
  }

  let body: React.ReactNode;
  if (loaded === null || loaded.productId !== productId) body = <p className="muted" role="status" style={{ fontSize: 13 }}>Loading the qualification…</p>;
  else if (!q) body = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
      <p className="form-error" role="alert" style={{ fontSize: 13, margin: 0 }}>Unable to load the qualification.</p>
      <button type="button" className="btn secondary small" onClick={() => setAttempt((n) => n + 1)}>Retry</button>
    </div>
  );
  else if (draft) body = (
    <form onSubmit={save} noValidate aria-label="Qualification form" style={{ display: "grid", gap: 12, marginTop: 8 }}>
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <ProductNote q={q} />
      {sections(q).map((section) => (
        <fieldset className="form-section" key={section.legend}>
          <legend>{section.legend}</legend>
          {section.product && q.product && (
            <p style={{ margin: 0 }}>
              <span className="muted">{section.product}: </span>
              <strong>{q.product.name}</strong> <span className="muted" style={{ fontSize: 13 }}>(change it in Lead details)</span>
            </p>
          )}
          <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
            {section.fields.map(control)}
          </div>
        </fieldset>
      ))}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save qualification"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={() => { setDraft(null); setErrors({}); setFailure(null); }}>Cancel</button>
      </div>
    </form>
  );
  else body = (
    <div style={{ display: "grid", gap: 12, marginTop: 8 }}>
      <ProductNote q={q} />
      {sections(q).map((section) => (
        <div key={section.legend}>
          <h4 style={{ margin: 0 }}>{section.legend}</h4>
          <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))", gap: "8px 16px", margin: "6px 0 0" }}>
            {section.product && q.product && (
              <div>
                <dt className="muted" style={{ fontSize: 13 }}>{section.product}</dt>
                <dd style={{ margin: 0 }}>{q.product.name}</dd>
              </div>
            )}
            {section.fields.map((field) => (
              <div key={field.key}>
                <dt className="muted" style={{ fontSize: 13 }}>{field.label}</dt>
                <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{shown(field, q[field.key] as string | number | null) ?? <span className="muted">Not recorded</span>}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
      {q.updated_by && q.updated_at && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Last updated by {q.updated_by.full_name} · {formatDate(q.updated_at, true)}</p>
      )}
    </div>
  );

  return (
    <section aria-labelledby="lead-qualification-heading">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id="lead-qualification-heading" style={{ margin: 0 }}>Qualification</h3>
        {q && !draft && !readOnly && !q.read_only && (
          <button type="button" className="btn secondary small" onClick={() => { setDraft(draftOf(q)); setErrors({}); setFailure(null); setSaved(false); }}>
            Edit qualification
          </button>
        )}
      </div>
      {body}
      {saved && !draft && <p className="form-message" role="status" style={{ margin: "6px 0 0", fontSize: 13 }}>Qualification saved.</p>}
    </section>
  );
}

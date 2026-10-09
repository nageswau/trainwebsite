"use client";
import { type FormEvent, type ReactNode, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { type CommissionTerm, CURRENCIES, termsUrl, TRIGGERS } from "@/lib/commissionTerms";
import type { PickOption } from "@/lib/lookups";
import { countrySearch } from "@/lib/universities";
import type { AgreementOptions } from "@/lib/universityAgreements";

// upc-016 (§15): one form for a new commission term and for editing one -- the 9 terms. Exactly one rate, a percentage or a fixed amount
// (CM2); switching sends the other as null. An edit sends only what changed. Empty programme / country picks mean "all" (CM5).
type Kind = "percent" | "fixed";
const TEXTS = { conditions: "Conditions", payment_terms: "Payment terms" } as const;
const SAVE_FAILED = "The commission term could not be saved. Try again.";

const sameIds = (a: string[], b: string[]) => a.length === b.length && a.every((id) => b.includes(id));

function startValues(t: CommissionTerm | null) {
  return {
    percent: t?.commission_percent ?? "", fixed: t?.fixed_amount ?? "", currency: t?.currency ?? "", trigger: t?.trigger ?? "",
    conditions: t?.conditions ?? "", payment_timeline: t?.payment_timeline ?? "", payment_terms: t?.payment_terms ?? "",
  };
}

export default function CommissionTermForm({ agreementId, options, term = null, label, onSaved, onCancel }: {
  agreementId: string; options: AgreementOptions; term?: CommissionTerm | null; label: string; onSaved: (message: string) => void; onCancel: () => void;
}) {
  const start = startValues(term);
  const startKind: Kind = term?.fixed_amount != null ? "fixed" : "percent";
  const [kind, setKind] = useState<Kind>(startKind);
  const [values, setValues] = useState(start);
  const [courseIds, setCourseIds] = useState<string[]>(() => term?.courses.map((c) => c.id) ?? []);
  const [countries, setCountries] = useState<PickOption[]>(() => term?.countries.map((c) => ({ id: c.id, label: c.name })) ?? []);
  const [pickerKey, setPickerKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const prefix = term ? `ct-${term.id}` : `ct-new-${agreementId}`;
  const set = (key: keyof typeof start) => (e: { target: { value: string } }) => setValues((v) => ({ ...v, [key]: e.target.value }));

  function problem(): string | null {
    const rate = kind === "percent" ? values.percent.trim() : values.fixed.trim();
    if (!rate) return kind === "percent" ? "Enter the commission percentage." : "Enter the fixed amount.";
    const n = Number(rate);
    if (kind === "percent" && !(n > 0 && n <= 100)) return "The commission percentage must be between 0 and 100.";
    if (kind === "fixed" && !(n > 0)) return "The fixed amount must be more than 0.";
    if (!values.currency) return "Choose the currency.";
    if (!values.trigger) return "Choose the commission trigger.";
    return null;
  }

  function body(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    const rateKey = kind === "percent" ? "commission_percent" : "fixed_amount";
    const rate = (kind === "percent" ? values.percent : values.fixed).trim();
    if (!term || kind !== startKind || rate !== (kind === "percent" ? start.percent : start.fixed)) out[rateKey] = rate;
    if (term && kind !== startKind) out[kind === "percent" ? "fixed_amount" : "commission_percent"] = null;
    for (const key of ["currency", "trigger", "conditions", "payment_timeline", "payment_terms"] as const) {
      const value = values[key].trim() || null; // blank = no value (an edit sends null to clear it)
      if (term ? value !== (start[key] || null) : value !== null) out[key] = value;
    }
    if (!term || !sameIds(courseIds, term.courses.map((c) => c.id))) out.course_ids = courseIds;
    const chosen = countries.map((c) => c.id);
    if (!term || !sameIds(chosen, term.countries.map((c) => c.id))) out.country_ids = chosen;
    return out;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const wrong = problem();
    if (wrong) return setError(wrong);
    const payload = body();
    if (term && Object.keys(payload).length === 0) return onSaved("No changes to save.");
    setError(null);
    setBusy(true);
    const outcome: SendOutcome = term ? await sendJson(termsUrl(agreementId, term.id), "PATCH", payload) : await sendJson(termsUrl(agreementId), "POST", payload);
    setBusy(false);
    if (outcome.ok) return onSaved(term ? "Commission term updated." : "Commission term added.");
    setError(outcome.status !== undefined && outcome.detail === undefined ? SAVE_FAILED : outcome.message);
  }

  const field = (key: string, text: string, input: ReactNode) => (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor={`${prefix}-${key}`}>{text}</label>
      {input}
    </div>
  );
  const grid = { display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" } as const;

  return (
    <form onSubmit={submit} noValidate aria-label={label} aria-busy={busy} className="card" style={{ padding: 14, display: "grid", gap: 12 }}>
      <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 12 }}>
        <fieldset style={{ border: 0, padding: 0, margin: 0, display: "flex", flexWrap: "wrap", gap: 16 }}>
          <legend style={{ fontWeight: 700, marginBottom: 6 }}>Commission (one of)</legend>
          {(["percent", "fixed"] as const).map((k) => (
            <label key={k} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <input type="radio" name={`${prefix}-kind`} value={k} checked={kind === k} onChange={() => setKind(k)} /> {k === "percent" ? "Percentage" : "Fixed amount"}
            </label>
          ))}
        </fieldset>
        <div style={grid}>
          {kind === "percent"
            ? field("percent", "Commission %", <input id={`${prefix}-percent`} type="number" inputMode="decimal" min="0.01" max="100" step="0.01" value={values.percent} onChange={set("percent")} />)
            : field("fixed", "Commission amount", <input id={`${prefix}-fixed`} type="number" inputMode="decimal" min="0.01" step="0.01" value={values.fixed} onChange={set("fixed")} />)}
          {field("currency", "Currency (required)", (
            <select id={`${prefix}-currency`} value={values.currency} onChange={set("currency")}>
              <option value="">Choose</option>
              {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          ))}
          {field("trigger", "Commission trigger (required)", (
            <select id={`${prefix}-trigger`} value={values.trigger} onChange={set("trigger")}>
              <option value="">Choose</option>
              {Object.entries(TRIGGERS).map(([key, word]) => <option key={key} value={key}>{word}</option>)}
            </select>
          ))}
        </div>
        {field("payment_timeline", "Payment timeline", (
          <input id={`${prefix}-payment_timeline`} value={values.payment_timeline} maxLength={500} onChange={set("payment_timeline")} placeholder="Within 60 days of the census date" />
        ))}
        <div style={grid}>
          {(Object.keys(TEXTS) as (keyof typeof TEXTS)[]).map((key) => (
            <div key={key}>{field(key, TEXTS[key], <textarea id={`${prefix}-${key}`} rows={3} maxLength={2000} value={values[key]} onChange={set(key)} />)}</div>
          ))}
        </div>
        <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 6 }}>
          <legend style={{ fontWeight: 700 }}>Eligible programmes</legend>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>Leave all unticked for every programme.</p>
          {options.courses.length === 0 ? <p className="muted" style={{ margin: 0 }}>No courses are recorded for this university yet.</p> : (
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
          )}
        </fieldset>
        <div style={{ display: "grid", gap: 8 }}>
          <strong>Eligible countries</strong>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>None chosen means students from every country.</p>
          {countries.length > 0 && (
            <ul aria-label="Eligible countries" style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexWrap: "wrap", gap: 8 }}>
              {countries.map((c) => (
                <li key={c.id} className="badge" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  {c.label}
                  <button type="button" className="btn ghost small" aria-label={`Remove ${c.label}`} onClick={() => setCountries((list) => list.filter((x) => x.id !== c.id))}>×</button>
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
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save term"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}

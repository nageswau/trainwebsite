"use client";

import { type FormEvent, useEffect, useId, useState } from "react";

import IntakePicker, { intakeProblem } from "@/components/IntakePicker";
import { EnglishTestRow } from "@/components/StudentProfileForm";
import { detailMessage, sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmTravel";
import LocalTime from "@/components/LocalTime";
import { formatCalendarDate } from "@/lib/formatDate";
import { MAX_ENGLISH_TESTS, TEST_STATUSES, emptyEnglishTest, fieldPlace, type CountryOption, type EnglishTest } from "@/lib/studentProfile";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useLeaveGuard } from "@/lib/useLeaveGuard";
import { BASIC_FIELDS, REQUIREMENT, qualificationUrl, type LeadQualification, type QualField, type QualKey } from "@/lib/telecallerLeads";

type Draft = Partial<Record<QualKey, string>>;
type Loaded = { productId: string | null; data: LeadQualification | "failed" } | null;
const COUNTRIES_URL = "/api/v1/public/countries"; // ccrm-005: the study destinations (ccrm-007's picker list)

// ccrm-005 (LF3): the English tests travel with the overseas answers; the row editor is ccrm-007's (strings while editing).
const testsOf = (q: LeadQualification): EnglishTest[] =>
  q.english_tests.map((t) => ({ ...t, overall_score: t.overall_score === null ? null : String(t.overall_score) }));
const testBody = (t: EnglishTest) => ({
  test_type: t.test_type, status: t.status || null, overall_score: t.overall_score ? Number(t.overall_score) : null,
  test_date: t.test_date || null, valid_until: t.valid_until || null, remarks: t.remarks?.trim() || null,
});
function testRefusal(detail: unknown): string | null {
  if (!Array.isArray(detail)) return null;
  const rows = detail.filter((item: { loc?: unknown }) => Array.isArray(item?.loc) && item.loc.includes("english_tests"));
  return rows.length ? rows.map((item: { loc?: unknown }) => [fieldPlace(item.loc), detailMessage([item])].filter(Boolean).join(": ")).join("; ") : null;
}
const testLine = (t: LeadQualification["english_tests"][number]) => [
  [t.test_type, t.overall_score].filter((v) => v !== null).join(" "), t.status ? TEST_STATUSES[t.status] : null,
  t.test_date ? `test ${formatCalendarDate(t.test_date)}` : null, t.valid_until ? `valid until ${formatCalendarDate(t.valid_until)}` : null, t.remarks,
].filter(Boolean).join(" · ");

// QD2: the fieldsets that apply to the lead's product group -- basic always, plus the IT or overseas requirement.
const sections = (q: LeadQualification) => {
  const group = q.product_group === "it" || q.product_group === "overseas" ? REQUIREMENT[q.product_group] : null;
  // `product` labels the lead's product (QF1: shown, changed in Lead details) -- "Course interested in" or "Destination"
  return [{ legend: "Basic qualification", fields: BASIC_FIELDS, product: null as string | null }, ...(group ? [group] : [])];
};
const applicable = (q: LeadQualification) => sections(q).flatMap((s) => s.fields);
const draftOf = (q: LeadQualification): Draft => Object.fromEntries(applicable(q).map((f) => [f.key, q[f.key] === null ? "" : String(q[f.key])]));
const overseas = (q: LeadQualification) => q.product_group === "overseas";
const shown = (field: QualField, q: LeadQualification) => {
  const value = q[field.key] as string | number | null;
  if (value === null || value === "") return null;
  if (field.kind === "country") return q.preferred_country?.name ?? null;
  return field.kind === "select" || field.kind === "radio" ? field.options.find((o) => o.value === value)?.label ?? value : value;
};

function ProductNote({ q }: { q: LeadQualification }) {
  if (!q.product) return <p className="muted" style={{ margin: 0, fontSize: 13 }}>Set the lead&apos;s product interest in Lead details to see its IT or overseas questions.</p>;
  if (q.product_group === "other") return <p className="muted" style={{ margin: 0, fontSize: 13 }}>{q.product.name} has no IT or overseas questions.</p>;
  return null;
}

/** tel-009 (spec §4; AC1-AC4; QF1, QD1-QD2): the lead's qualification -- read on open and again whenever the lead's product changes (the
 *  section follows the saved product; the other group's values stay stored, hidden). A read-only lead shows the view only. A save
 *  hands the result back, so the panel's Lead details show the shared answers (qualification, passing year, city, state). */
export default function LeadQualificationForm({ leadId, url = qualificationUrl(leadId), productId, readOnly, onSaved }: {
  leadId: string; url?: string; productId: string | null; readOnly: boolean; onSaved: (q: LeadQualification) => void;
}) {
  const idp = useId();
  const [loaded, setLoaded] = useState<Loaded>(null);
  const [attempt, setAttempt] = useState(0);
  const [draft, setDraft] = useState<Draft | null>(null); // null = viewing
  const [tests, setTests] = useState<EnglishTest[]>([]); // ccrm-005: the English tests being edited (with the draft)
  const [countries, setCountries] = useState<CountryOption[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // ccrm-005: a failed list leaves only the saved country choosable (the form still works)
    const controller = new AbortController();
    fetch(COUNTRIES_URL, { signal: controller.signal })
      .then(async (response) => (response.ok ? ((await response.json()) as CountryOption[]) : []))
      .then((list) => setCountries(Array.isArray(list) ? list.map((c) => ({ id: c.id, name: c.name })) : []))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch(url, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Request failed (${response.status})`);
        setLoaded({ productId, data: (await response.json()) as LeadQualification });
      })
      .catch(() => controller.signal.aborted || setLoaded({ productId, data: "failed" }));
    setDraft(null); // a product change while editing re-lays the form from the saved product
    return () => controller.abort();
  }, [url, productId, attempt]);

  const q = loaded && loaded.productId === productId && loaded.data !== "failed" ? loaded.data : null;
  const dirty = !!q && !!draft && (JSON.stringify(draft) !== JSON.stringify(draftOf(q)) || JSON.stringify(tests) !== JSON.stringify(testsOf(q)));
  useLeaveGuard(dirty && !busy, "Discard the qualification changes?");
  const startEditing = (data: LeadQualification) => {
    setDraft(draftOf(data));
    setTests(testsOf(data));
    setErrors({});
    setFailure(null);
    setSaved(false);
  };

  const focus = useFocusAfterRender();
  const fieldId = (key: string) => `${idp}-${key}`;
  const errorId = (key: string) => `${idp}-${key}-error`;
  const set = (key: QualKey, value: string) => {
    setDraft((d) => ({ ...d, [key]: value }));
    setSaved(false);
  };

  // QA-01: focus the first refused field in form order, else the message (a radio group has no element with its id)
  function refuse(found: Record<string, string>, message: string) {
    setErrors(found);
    setFailure(message);
    const first = q ? applicable(q).find((f) => found[f.key]) : undefined;
    focus(...(first ? [fieldId(first.key)] : []), fieldId("message"));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!q || !draft) return;
    const body: Record<string, string | number | null | ReturnType<typeof testBody>[]> = overseas(q) ? { english_tests: tests.map(testBody) } : {};
    const local: Record<string, string> = {};
    for (const field of applicable(q)) {
      const text = (draft[field.key] ?? "").trim();
      const intakeError = field.kind === "intake" ? intakeProblem(text, q.intake) : null; // ccrm-047: a legacy value left as it was is fine
      if (intakeError) local[field.key] = intakeError;
      if (field.kind !== "number") body[field.key] = text || null;
      else if (!text) body[field.key] = null;
      else {
        const value = Number(text);
        // ccrm-005 QA-01: count the typed decimals -- 8.2 * 100 is 819.999… in floating point
        const whole = field.step === 1 ? Number.isInteger(value) : /^-?\d*(\.\d{0,2})?$/.test(text);
        if (!Number.isFinite(value) || !whole || value < field.min || value > field.max) local[field.key] = field.error;
        body[field.key] = value;
      }
    }
    if (Object.keys(local).length) return refuse(local, "Check the highlighted fields.");
    setErrors({});
    setBusy(true);
    const outcome = await sendJson(url, "PUT", body);
    setBusy(false);
    if (!outcome.ok) {
      const tested = testRefusal(outcome.detail); // ccrm-005: a refused English test row is named ("English test 2 · Overall score: …")
      if (tested) return refuse({}, tested);
      const mapped = fieldErrors(outcome.detail);
      return refuse(mapped, Object.keys(mapped).length ? "Check the highlighted fields." : outcome.message);
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
    if (field.kind === "intake") {
      return (
        <div key={field.key} style={{ display: "grid", gap: 4 }}>
          <IntakePicker id={fieldId(field.key)} label={field.label} value={value} disabled={busy} onChange={(v) => set(field.key, v)} />
          {error}
        </div>
      );
    }
    return (
      <div className="field" key={field.key}>
        <label htmlFor={fieldId(field.key)}>{field.label}</label>
        {field.kind === "select" || field.kind === "country" ? (
          <select id={fieldId(field.key)} value={value} disabled={busy} onChange={(e) => set(field.key, e.target.value)} {...invalid}>
            <option value="">Not recorded</option>
            {(field.kind === "country" ? countryOptions : field.options).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
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

  // the saved country stays choosable when the public list does not have it (or failed to load)
  const savedCountry = q?.preferred_country && !countries.some((c) => c.id === q.preferred_country?.id) ? [q.preferred_country] : [];
  const countryOptions = [...savedCountry, ...countries].map((c) => ({ value: c.id, label: c.name }));

  // ccrm-005 (LF3): the overseas group's English tests -- ccrm-007's row editor, at most five
  const testsEditor = (
    <div role="group" aria-label="English tests" style={{ display: "grid", gap: 12 }}>
      <strong>English tests</strong>
      {tests.length === 0 && <p className="muted" style={{ margin: 0 }}>No English tests added.</p>}
      {tests.map((t, i) => (
        <EnglishTestRow key={i} index={i} row={t} onChange={(change) => setTests((all) => all.map((row, j) => (j === i ? { ...row, ...change } : row)))}
          onRemove={() => setTests((all) => all.filter((_, j) => j !== i))} />
      ))}
      {tests.length < MAX_ENGLISH_TESTS ? (
        <button type="button" className="btn secondary small" style={{ justifySelf: "start" }} disabled={busy}
          onClick={() => setTests((all) => [...all, emptyEnglishTest()])}>Add English test</button>
      ) : <p className="muted" style={{ margin: 0, fontSize: 13 }}>Up to {MAX_ENGLISH_TESTS} English tests.</p>}
    </div>
  );
  const testsView = q && (
    <div>
      <dt className="muted" style={{ fontSize: 13 }}>English tests</dt>
      <dd style={{ margin: 0 }}>
        {q.english_tests.length === 0 ? <span className="muted">Not recorded</span> : (
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {q.english_tests.map((t, i) => (
              <li key={i} style={{ overflowWrap: "anywhere" }}>{testLine(t)} {t.expired && <span className="status error">Expired</span>}</li>
            ))}
          </ul>
        )}
      </dd>
    </div>
  );

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
      {failure && <p id={fieldId("message")} tabIndex={-1} className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
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
          {section.legend === REQUIREMENT.overseas.legend && testsEditor}
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
                <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{shown(field, q) ?? <span className="muted">Not recorded</span>}</dd>
              </div>
            ))}
            {section.legend === REQUIREMENT.overseas.legend && testsView}
          </dl>
        </div>
      ))}
      {q.updated_by && q.updated_at && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Last updated by {q.updated_by.full_name} · <LocalTime value={q.updated_at} time /></p>
      )}
    </div>
  );

  return (
    <section aria-labelledby="lead-qualification-heading">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id="lead-qualification-heading" style={{ margin: 0 }}>Qualification</h3>
        {q && !draft && !readOnly && !q.read_only && (
          <button type="button" className="btn secondary small" onClick={() => startEditing(q)}>
            Edit qualification
          </button>
        )}
      </div>
      {body}
      {saved && !draft && <p className="form-message" role="status" style={{ margin: "6px 0 0", fontSize: 13 }}>Qualification saved.</p>}
    </section>
  );
}

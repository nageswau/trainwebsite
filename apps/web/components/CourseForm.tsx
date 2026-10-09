"use client";
import { type FormEvent, type ReactNode, useState } from "react";

import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { type Course, type CourseOptions, coursesUrl, CURRENCIES, ENGLISH_TESTS, LEVELS, MONTHS, scoreProblem } from "@/lib/courseMaster";

// upc-017 (§16): one form for a new course and for editing one -- the 14 fields. An edit sends only what changed; a legacy level
// ("Masters") is shown as it is and only replaced when another level is chosen (CO3). The commission block is for the commission roles
// only (U2; the API refuses everyone else). `noValidate`: the form's own messages are the ones read out.
type RateKind = "none" | "percent" | "amount";
const TEXTS = { entry_requirements: "Entry requirements", application_process: "Application process" } as const;
const PAIRS = [["tuition_amount", "tuition_currency", "tuition fee"], ["application_fee", "application_fee_currency", "application fee"]] as const;
const SAVE_FAILED = "The course could not be saved. Try again.";
const MONEY = /^\d+(\.\d{1,2})?$/;

function startValues(c: Course | null) {
  return {
    title: c?.title ?? "", level: c?.level ?? "", category: c?.category ?? "", duration: c?.duration ?? "",
    tuition_amount: c?.tuition_amount ?? "", tuition_currency: c?.tuition_currency ?? "", application_fee: c?.application_fee ?? "",
    application_fee_currency: c?.application_fee_currency ?? "", english_test: c?.english_test ?? "", english_score: c?.english_score ?? "",
    entry_requirements: c?.entry_requirements ?? "", application_process: c?.application_process ?? "", deadline: c?.deadline ?? "",
  };
}
type Values = ReturnType<typeof startValues>;

function startRate(c: Course | null): { kind: RateKind; percent: string; amount: string; currency: string } {
  const rate = c?.commission;
  if (!rate) return { kind: "none", percent: "", amount: "", currency: "" };
  return rate.percent !== null ? { kind: "percent", percent: rate.percent, amount: "", currency: "" } : { kind: "amount", percent: "", amount: rate.amount ?? "", currency: rate.currency ?? "" };
}

/** The rate as one comparable value ("12.50" and "12.5" are the same rate). */
const rateKey = (r: ReturnType<typeof startRate>) =>
  r.kind === "none" ? "none" : r.kind === "percent" ? `percent:${Number(r.percent)}` : `amount:${Number(r.amount)}:${r.currency}`;

function problem(v: Values, rate: ReturnType<typeof startRate>, canSetCommission: boolean): string | null {
  for (const [key, word] of [["title", "the course title"], ["level", "the level"], ["category", "the category"], ["duration", "the duration"]] as const) {
    if (!v[key].trim()) return `Enter ${word}.`;
  }
  for (const [amount, currency, word] of PAIRS) {
    const value = v[amount].trim();
    if (value && Number(value) < 0) return `The ${word} cannot be negative.`;
    if (value && !MONEY.test(value)) return `Use a number with at most two decimal places for the ${word}.`;
    if (Boolean(value) !== Boolean(v[currency])) return `Enter both the ${word} and its currency, or neither.`;
  }
  const score = scoreProblem(v.english_test, v.english_score);
  if (score) return score;
  if (canSetCommission && rate.kind !== "none") {
    const value = (rate.kind === "percent" ? rate.percent : rate.amount).trim();
    const n = Number(value);
    if (!value || !MONEY.test(value) || !(n > 0)) return "Enter a commission above 0 with at most two decimal places.";
    if (rate.kind === "percent" && n > 100) return "The commission percentage cannot be above 100.";
    if (rate.kind === "amount" && !rate.currency) return "Choose the commission currency.";
  }
  return null;
}

const sameList = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));

export default function CourseForm({ universityId, options, course = null, canSetCommission, label, onSaved, onCancel }: {
  universityId: string; options: CourseOptions; course?: Course | null; canSetCommission: boolean; label: string;
  onSaved: (message: string) => void; onCancel: () => void;
}) {
  const start = startValues(course);
  const [values, setValues] = useState(start);
  const [intakes, setIntakes] = useState<string[]>(() => course?.intakes ?? []);
  const [scholarshipIds, setScholarshipIds] = useState<string[]>(() => course?.scholarships.map((s) => s.id) ?? []);
  const [active, setActive] = useState(course?.active ?? true);
  const rateStart = startRate(course);
  const [rate, setRate] = useState(rateStart);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const prefix = course ? `course-${course.id}` : `course-new-${universityId}`;
  const set = (key: keyof Values) => (e: { target: { value: string } }) => setValues((v) => ({ ...v, [key]: e.target.value }));
  const legacyLevel = course && !(LEVELS as readonly string[]).includes(course.level) ? course.level : null;

  function body(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(start) as (keyof Values)[]) {
      const value = values[key].trim() || null; // blank = no value (an edit sends null to clear it)
      if (course ? value !== (start[key] || null) : value !== null) out[key] = value;
    }
    const months = MONTHS.filter((m) => intakes.includes(m)); // calendar order, as the API stores them
    if (course ? !sameList(months, course.intakes) : months.length) out.intakes = months;
    if (course ? !sameList(scholarshipIds, course.scholarships.map((s) => s.id)) : scholarshipIds.length) out.scholarship_ids = scholarshipIds;
    if (!course || active !== course.active) out.active = active;
    if (canSetCommission && rateKey(rate) !== rateKey(rateStart)) {
      out.commission = rate.kind === "none" ? null : rate.kind === "percent" ? { percent: rate.percent.trim() } : { amount: rate.amount.trim(), currency: rate.currency };
    }
    return out;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const wrong = problem(values, rate, canSetCommission);
    if (wrong) return setError(wrong);
    const payload = body();
    if (course && Object.keys(payload).length === 0) return onSaved("No changes to save.");
    setError(null);
    setBusy(true);
    const outcome: SendOutcome = course ? await sendJson(coursesUrl(universityId, course.id), "PATCH", payload) : await sendJson(coursesUrl(universityId), "POST", payload);
    setBusy(false);
    if (outcome.ok) return onSaved(course ? "Course updated." : "Course added.");
    setError(outcome.status !== undefined && outcome.detail === undefined ? SAVE_FAILED : outcome.message);
  }

  const field = (key: string, text: string, input: ReactNode) => (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor={`${prefix}-${key}`}>{text}</label>
      {input}
    </div>
  );
  const money = (key: "tuition_amount" | "application_fee", text: string) =>
    field(key, text, <input id={`${prefix}-${key}`} type="number" inputMode="decimal" min="0" step="0.01" value={values[key]} onChange={set(key)} />);
  const currency = (key: "tuition_currency" | "application_fee_currency", text: string) =>
    field(key, text, (
      <select id={`${prefix}-${key}`} value={values[key]} onChange={set(key)}>
        <option value="">Choose</option>
        {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
    ));
  const grid = { display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" } as const;
  const plain = { border: 0, padding: 0, margin: 0 } as const;

  return (
    <form onSubmit={submit} noValidate aria-label={label} aria-busy={busy} className="card" style={{ padding: 14, display: "grid", gap: 12 }}>
      <fieldset disabled={busy} style={{ ...plain, display: "grid", gap: 12 }}>
        <div style={grid}>
          {field("title", "Course title (required)", <input id={`${prefix}-title`} autoFocus value={values.title} maxLength={200} onChange={set("title")} placeholder="MSc Cyber Security" />)}
          {field("level", "Level (required)", (
            <select id={`${prefix}-level`} value={values.level} onChange={set("level")}>
              <option value="">Choose</option>
              {legacyLevel && <option value={legacyLevel}>{legacyLevel} (old value — choose a level)</option>}
              {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          ))}
          {field("category", "Category (required)", <input id={`${prefix}-category`} value={values.category} maxLength={80} onChange={set("category")} placeholder="Computer Science" />)}
          {field("duration", "Duration (required)", <input id={`${prefix}-duration`} value={values.duration} maxLength={80} onChange={set("duration")} placeholder="1 year" />)}
        </div>
        <fieldset style={{ ...plain, display: "grid", gap: 6 }}>
          <legend style={{ fontWeight: 700, marginBottom: 6 }}>Intakes</legend>
          <ul className="list-clean" style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", margin: 0 }}>
            {MONTHS.map((m) => (
              <li key={m}>
                <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                  <input type="checkbox" checked={intakes.includes(m)} onChange={(e) => setIntakes((list) => (e.target.checked ? [...list, m] : list.filter((x) => x !== m)))} />
                  {m}
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
        <div style={grid}>
          {money("tuition_amount", "Tuition fee")}
          {currency("tuition_currency", "Tuition currency")}
          {money("application_fee", "Application fee")}
          {currency("application_fee_currency", "Application fee currency")}
        </div>
        <div style={grid}>
          {field("english_test", "English test", (
            <select id={`${prefix}-english_test`} value={values.english_test} onChange={set("english_test")}>
              <option value="">None</option>
              {ENGLISH_TESTS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          ))}
          {field("english_score", "Minimum score", <input id={`${prefix}-english_score`} type="number" inputMode="decimal" min="0" step="0.1" value={values.english_score} onChange={set("english_score")} />)}
          {field("deadline", "Application deadline", <input id={`${prefix}-deadline`} type="date" value={values.deadline} onChange={set("deadline")} />)}
        </div>
        <div style={grid}>
          {(Object.keys(TEXTS) as (keyof typeof TEXTS)[]).map((key) => (
            <div key={key}>{field(key, TEXTS[key], <textarea id={`${prefix}-${key}`} rows={3} maxLength={2000} value={values[key]} onChange={set(key)} />)}</div>
          ))}
        </div>
        <fieldset style={{ ...plain, display: "grid", gap: 6 }}>
          <legend style={{ fontWeight: 700 }}>Scholarships</legend>
          {options.scholarships.length === 0 ? <p className="muted" style={{ margin: 0 }}>No scholarships are recorded for this university or its country.</p> : (
            <ul className="list-clean" style={{ display: "grid", gap: 4, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", margin: 0 }}>
              {options.scholarships.map((s) => (
                <li key={s.id}>
                  <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                    <input type="checkbox" checked={scholarshipIds.includes(s.id)}
                      onChange={(e) => setScholarshipIds((ids) => (e.target.checked ? [...ids, s.id] : ids.filter((id) => id !== s.id)))} />
                    {s.title} <span className="muted">({s.amount})</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </fieldset>
        {canSetCommission && (
          <fieldset style={{ ...plain, display: "grid", gap: 8 }}>
            <legend style={{ fontWeight: 700, marginBottom: 6 }}>Commission <span className="badge">Restricted</span></legend>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
              {(["none", "percent", "amount"] as const).map((k) => (
                <label key={k} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                  <input type="radio" name={`${prefix}-rate`} value={k} checked={rate.kind === k} onChange={() => setRate((r) => ({ ...r, kind: k }))} />
                  {{ none: "Not recorded", percent: "Percentage", amount: "Amount" }[k]}
                </label>
              ))}
            </div>
            {rate.kind === "percent" && field("commission_percent", "Commission %", (
              <input id={`${prefix}-commission_percent`} type="number" inputMode="decimal" min="0.01" max="100" step="0.01" value={rate.percent} onChange={(e) => setRate((r) => ({ ...r, percent: e.target.value }))} />
            ))}
            {rate.kind === "amount" && (
              <div style={grid}>
                {field("commission_amount", "Commission amount", (
                  <input id={`${prefix}-commission_amount`} type="number" inputMode="decimal" min="0.01" step="0.01" value={rate.amount} onChange={(e) => setRate((r) => ({ ...r, amount: e.target.value }))} />
                ))}
                {field("commission_currency", "Commission currency", (
                  <select id={`${prefix}-commission_currency`} value={rate.currency} onChange={(e) => setRate((r) => ({ ...r, currency: e.target.value }))}>
                    <option value="">Choose</option>
                    {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                ))}
              </div>
            )}
          </fieldset>
        )}
        <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Offered (active)
        </label>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>An inactive course leaves the public catalogue; applications that name it keep it.</p>
      </fieldset>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save course"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}

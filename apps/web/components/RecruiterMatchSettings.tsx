"use client";

import { type FormEvent, useEffect, useId, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { FACTOR_LABEL, FACTORS, type FactorKey, type FactorWeights, isMatchSettings, MATCH_SETTINGS_URL, type MatchSettings } from "@/lib/recruiterMatching";

// hrc-018 (DEC-SCOPE-392 E2/E3; AC1): the match factor weights -- shown only to who may change them (super_admin; the hrc-012/022 setting
// card idiom). The total must be exactly 100 before Save is offered; the API and the database re-check it.
const toText = (w: FactorWeights) => Object.fromEntries(FACTORS.map((f) => [f, String(w[f])])) as Record<FactorKey, string>;
const whole = (text: string) => /^\d{1,3}$/.test(text.trim()) && Number(text) <= 100;

export default function RecruiterMatchSettings() {
  const [setting, setSetting] = useState<MatchSettings | null>(null);
  const [values, setValues] = useState<Record<FactorKey, string> | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const id = useId();

  useEffect(() => {
    const controller = new AbortController();
    fetch(MATCH_SETTINGS_URL, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((s: unknown) => {
        if (!isMatchSettings(s)) return;
        setSetting(s);
        setValues(toText(s.weights));
      })
      .catch(() => undefined); // a failed read leaves the card hidden; the list keeps working
    return () => controller.abort();
  }, []);

  if (!setting?.can_edit || !values) return null;
  const valid = FACTORS.every((f) => whole(values[f]));
  const total = valid ? FACTORS.reduce((sum, f) => sum + Number(values[f]), 0) : null;

  async function save(event: FormEvent) {
    event.preventDefault();
    if (busy || total !== 100 || !values) return;
    setBusy(true);
    setMessage(null);
    const weights = Object.fromEntries(FACTORS.map((f) => [f, Number(values[f])]));
    const outcome = await sendJson(MATCH_SETTINGS_URL, "PUT", { weights });
    setBusy(false);
    if (!outcome.ok || !isMatchSettings(outcome.data)) {
      return setMessage({ text: outcome.ok ? "Unable to save the weights." : outcome.message, failed: true });
    }
    setSetting(outcome.data);
    setValues(toText(outcome.data.weights));
    setMessage({ text: "Match weights saved. Every requirement's matches now use them.", failed: false });
  }

  const summary = FACTORS.map((f) => `${FACTOR_LABEL[f]} ${setting.weights[f]}`).join(" · ");
  return (
    <details className="action-card" style={{ marginBottom: 16 }}>
      <summary style={{ cursor: "pointer" }}>
        <strong>Match weights</strong>
        <span className="muted" style={{ display: "block", fontSize: 13 }}>How much each factor counts in a candidate&apos;s match score: {summary}.</span>
      </summary>
      <form onSubmit={save} aria-label="Match weights" noValidate style={{ marginTop: 12 }}>
        <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fill, minmax(10rem, 1fr))" }}>
          {FACTORS.map((f) => (
            <div key={f} className="field" style={{ marginBottom: 0 }}>
              <label htmlFor={`${id}-${f}`}>{FACTOR_LABEL[f]}</label>
              <input id={`${id}-${f}`} type="number" inputMode="numeric" min={0} max={100} step={1} value={values[f]} disabled={busy}
                aria-invalid={!whole(values[f])} onChange={(e) => setValues((v) => v && { ...v, [f]: e.target.value })} />
            </div>
          ))}
        </div>
        <p role="status" aria-live="polite" className={total === 100 ? "muted" : "form-error"} style={{ fontSize: 13, margin: "10px 0" }}>
          {total === null ? "Each weight must be a whole number from 0 to 100." : `Total ${total} of 100${total === 100 ? "." : " — the weights must add up to 100."}`}
        </p>
        <p className="muted" style={{ fontSize: 13, margin: "0 0 10px" }}>
          A factor a requirement has no details for is left out, and the others share its points. A score is a guide, not a guarantee.
        </p>
        {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} style={{ margin: "0 0 8px" }}>{message.text}</p>}
        <div className="actions" style={{ flexWrap: "wrap", gap: 8 }}>
          <button className="btn small" type="submit" disabled={busy || total !== 100}>{busy ? "Saving…" : "Save weights"}</button>
          <button className="btn secondary small" type="button" disabled={busy} onClick={() => setValues(toText(setting.defaults))}>Use the defaults</button>
        </div>
      </form>
    </details>
  );
}

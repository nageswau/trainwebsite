"use client";
import { useCallback, useEffect, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import { EXCHANGE_RATES_URL, type ExchangeRate } from "@/lib/recruiterCatalogue";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "fx-rate-feedback";
const CURRENCY_ID = "fx-rate-currency";

// hrc-011 (DEC-SCOPE-375 C1/C5): the manager's manual exchange rates -- one form that adds or changes a rate (the API recomputes every
// candidate's yearly rupee figure in that currency), and the list with loading / error+Retry / empty states. Rates are never deleted.
export default function RecruiterExchangeRatesPanel() {
  const [rates, setRates] = useState<ExchangeRate[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [form, setForm] = useState({ currency: "", rate: "" });
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const inFlight = useRef(false); // a double click must not PUT twice
  const focus = useFocusAfterRender();

  const load = useCallback(() => {
    setFailed(false);
    fetch(EXCHANGE_RATES_URL)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: { items: ExchangeRate[] }) => setRates(data.items))
      .catch(() => setFailed(true));
  }, []);
  useEffect(load, [load]);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const currency = form.currency.trim().toUpperCase();
    if (!/^[A-Z]{3}$/.test(currency) || !form.rate.trim()) {
      setFeedback({ text: "Enter a three-letter currency code (such as USD) and the rupees for one unit.", tone: "error" });
      return focus(FEEDBACK_ID);
    }
    inFlight.current = true;
    setBusy(true);
    const outcome = await sendJson(`${EXCHANGE_RATES_URL}/${encodeURIComponent(currency)}`, "PUT", { inr_per_unit: form.rate.trim() });
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback({ text: `Saved: 1 ${currency} = ₹${Number(form.rate)}. Candidates paid in ${currency} now use this rate.`, tone: "success" });
      setForm({ currency: "", rate: "" });
      load();
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  function edit(rate: ExchangeRate) {
    setForm({ currency: rate.currency, rate: String(Number(rate.inr_per_unit)) });
    setFeedback(null);
    focus(CURRENCY_ID);
  }

  return (
    <>
      <form className="action-card form" onSubmit={save} aria-describedby={FEEDBACK_ID} noValidate>
        <h3>Add or change a rate</h3>
        <div className="field">
          <label htmlFor={CURRENCY_ID}>Currency code (required)</label>
          <input id={CURRENCY_ID} value={form.currency} maxLength={3} autoCapitalize="characters" placeholder="USD" disabled={busy}
            onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value }))} />
        </div>
        <div className="field">
          <label htmlFor="fx-rate-value">Rupees for 1 unit (required)</label>
          <input id="fx-rate-value" type="number" min={0.0001} max={10000} step="0.0001" inputMode="decimal" value={form.rate} disabled={busy}
            onChange={(e) => setForm((f) => ({ ...f, rate: e.target.value }))} />
        </div>
        <button className="btn" disabled={busy}>{busy ? "Saving…" : "Save rate"}</button>
        <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
      </form>
      <section className="action-card" aria-labelledby="fx-rates-heading">
        <h3 id="fx-rates-heading">Exchange rates</h3>
        {failed ? (
          <p className="form-error" role="alert">Unable to load the exchange rates. <button type="button" className="btn secondary small" onClick={load}>Retry</button></p>
        ) : rates === null ? (
          <p className="muted" role="status">Loading…</p>
        ) : rates.length === 0 ? (
          <p className="muted">No rates yet. INR needs none; add a rate before entering pay in another currency.</p>
        ) : (
          <div className="table-wrap">
            <table className="table compact stack">
              <thead><tr><th scope="col">Currency</th><th scope="col">Rupees for 1 unit</th><th scope="col">Last changed</th><th scope="col"><span className="visually-hidden">Actions</span></th></tr></thead>
              <tbody>
                {rates.map((r) => (
                  <tr key={r.currency}>
                    <td data-label="Currency"><strong>{r.currency}</strong></td>
                    <td data-label="Rupees for 1 unit">₹{Number(r.inr_per_unit).toLocaleString("en-IN", { maximumFractionDigits: 4 })}</td>
                    <td data-label="Last changed"><span>{/* QA-01: one value, so a stacked row keeps date and author together */}<LocalTime value={r.updated_at} time />{r.updated_by ? ` by ${r.updated_by.full_name}` : ""}</span></td>
                    <td><button type="button" className="btn secondary small" onClick={() => edit(r)} aria-label={`Change the ${r.currency} rate`}>Change</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

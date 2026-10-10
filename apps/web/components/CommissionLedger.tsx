"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import {
  applicationLabel,
  type CommissionLedger as Ledger,
  type CommissionReceipt,
  CURRENCIES,
  moneyText,
  receiptsUrl,
} from "@/lib/commissionLedger";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// upc-019 (§15 "Finance manages actual receipts", §18 F10/F11): a university's commission ledger -- RESTRICTED (U2). The page renders it
// only for the commission roles; the API is the gate. Totals are per currency (no FX). The head / super_admin record and remove receipts
// (Q-20); every success re-reads the page (router.refresh). Applications are never named by student (CL14). Data-only props.
const SAVE_FAILED = "The receipt could not be saved. Try again.";
const REMOVE_FAILED = "The receipt could not be removed. Try again.";
const EMPTY_FORM = { amount: "", currency: "", reference: "", note: "" };

export default function CommissionLedger({ ledger, today }: { ledger: Ledger; today: string }) {
  const router = useRouter();
  const sending = useRef(false);
  const focus = useFocusAfterRender();
  const [open, setOpen] = useState<string | null>(null); // "new", "<receipt id>:remove", or null
  const [values, setValues] = useState({ ...EMPTY_FORM, received_on: today });
  const [linked, setLinked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { university: uni, permissions } = ledger;
  const recordId = `cl-${uni.id}-record`;
  const headingId = `cl-${uni.id}-heading`;
  const set = (key: keyof typeof values) => (e: { target: { value: string } }) => setValues((v) => ({ ...v, [key]: e.target.value }));

  const show = (key: string | null) => {
    setOpen(key);
    setFailure(null);
    setNotice(null);
  };
  const done = (message: string) => {
    show(null);
    setValues({ ...EMPTY_FORM, received_on: today });
    setLinked([]);
    setNotice(message);
    focus(recordId, headingId); // the control that had focus is gone
    router.refresh();
  };

  function problem(): string | null {
    const amount = values.amount.trim();
    if (!amount) return "Enter the amount received.";
    if (!(Number(amount) > 0)) return "The amount must be more than 0.";
    if (!/^\d+(\.\d{1,2})?$/.test(amount)) return "Use at most two decimal places.";
    if (!values.currency) return "Choose the currency.";
    if (!values.reference.trim()) return "Enter the payment reference.";
    if (!values.received_on) return "Enter the date received.";
    if (values.received_on > today) return "The date received can't be in the future.";
    return null;
  }

  async function run(request: () => ReturnType<typeof sendRequest>, ok: string, failed: string) {
    if (sending.current) return; // one request at a time: a double click never records twice
    sending.current = true;
    setBusy(true);
    setFailure(null);
    const outcome = await request();
    sending.current = false;
    setBusy(false);
    if (outcome.ok) return done(ok);
    setFailure(outcome.status !== undefined && outcome.detail === undefined ? failed : outcome.message);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const wrong = problem();
    if (wrong) return setFailure(wrong);
    const body = { amount: values.amount.trim(), currency: values.currency, received_on: values.received_on, reference: values.reference.trim(), note: values.note.trim() || null, application_ids: linked };
    void run(() => sendJson(receiptsUrl(uni.id), "POST", body), "Receipt recorded.", SAVE_FAILED);
  }

  const remove = (r: CommissionReceipt) => run(() => sendRequest(receiptsUrl(uni.id, r.id), { method: "DELETE" }), "Receipt removed.", REMOVE_FAILED);
  const field = { margin: 0 } as const;
  const grid = { display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" } as const;

  return (
    <section className="action-card wide" aria-label="Commission (restricted)" style={{ display: "grid", gap: 12 }}>
      <h3 id={headingId} tabIndex={-1}>Commission <span className="badge">Restricted</span></h3>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Expected counts enrolled applications whose commission trigger is met, under the agreement in force on the enrolment day. Totals are per currency; nothing is converted.
      </p>

      {ledger.totals.length === 0 ? <p className="muted" style={{ margin: 0 }}>No commission expected or received yet.</p> : (
        <div className="table-scroll" role="region" aria-label="Commission by currency, scrollable" tabIndex={0}>
          <table className="table">
            <caption className="visually-hidden">Commission by currency</caption>
            <thead><tr><th scope="col">Currency</th><th scope="col">Expected</th><th scope="col">Received</th><th scope="col">Outstanding</th></tr></thead>
            <tbody>
              {ledger.totals.map((t) => (
                <tr key={t.currency}>
                  <th scope="row">{t.currency}</th>
                  <td>{moneyText(t.currency, t.expected)}</td>
                  <td>{moneyText(t.currency, t.received)}</td>
                  <td>{moneyText(t.currency, t.outstanding)}{Number(t.outstanding) < 0 && <span className="muted"> (received more than expected)</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h4 style={{ margin: 0 }}>Enrolled applications</h4>
      {ledger.applications.length === 0 ? <p className="muted" style={{ margin: 0 }}>No enrolled applications yet.</p> : (
        <>
          <div className="table-scroll" role="region" aria-label="Enrolled applications, scrollable" tabIndex={0}>
            <table className="table">
              <caption className="visually-hidden">Enrolled applications and their expected commission</caption>
              <thead><tr><th scope="col">Application</th><th scope="col">Enrolled on</th><th scope="col">Status</th><th scope="col">Expected</th></tr></thead>
              <tbody>
                {ledger.applications.map((a) => (
                  <tr key={a.id}>
                    <th scope="row" style={{ fontWeight: 400 }}>{applicationLabel(a)}</th>
                    <td>{a.enrolled_on ?? "—"}</td>
                    <td>{a.status === "counted" ? a.status_label : <span className="muted">{a.status_label}</span>}</td>
                    <td>{a.amount && a.currency ? moneyText(a.currency, a.amount) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {ledger.applications_total > ledger.applications.length && (
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>Showing the latest {ledger.applications.length} of {ledger.applications_total} enrolled applications; the totals count them all.</p>
          )}
        </>
      )}

      <h4 style={{ margin: 0 }}>Commission received</h4>
      {ledger.receipts.length === 0 ? <p className="muted" style={{ margin: 0 }}>No receipts recorded yet.</p> : (
        <div className="table-scroll" role="region" aria-label="Commission received, scrollable" tabIndex={0}>
          <table className="table">
            <caption className="visually-hidden">Commission received</caption>
            <thead>
              <tr>
                <th scope="col">Date received</th><th scope="col">Amount</th><th scope="col">Reference</th><th scope="col">Note</th>
                <th scope="col">Linked applications</th><th scope="col">Recorded by</th>{permissions.can_record && <th scope="col"><span className="visually-hidden">Actions</span></th>}
              </tr>
            </thead>
            <tbody>
              {ledger.receipts.map((r) => (
                <tr key={r.id}>
                  <td>{r.received_on}</td>
                  <td>{moneyText(r.currency, r.amount)}</td>
                  <th scope="row" style={{ fontWeight: 400, overflowWrap: "anywhere" }}>{r.reference}</th>
                  <td style={{ overflowWrap: "anywhere", whiteSpace: "pre-line" }}>{r.note ?? "—"}</td>
                  <td>{r.application_ids.length || "—"}</td>
                  <td>{r.created_by.full_name}</td>
                  {permissions.can_record && (
                    <td>
                      {open === `${r.id}:remove` ? (
                        <div className="actions" role="group" aria-label={`Remove receipt ${r.reference}?`}>
                          <button type="button" className="btn small" onClick={() => void remove(r)} disabled={busy} autoFocus>{busy ? "Removing…" : "Yes, remove"}</button>
                          <button type="button" className="btn secondary small" onClick={() => show(null)} disabled={busy}>Cancel</button>
                        </div>
                      ) : (
                        <button type="button" className="btn ghost small" onClick={() => show(`${r.id}:remove`)} disabled={busy} aria-label={`Remove receipt ${r.reference}`}>Remove</button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {ledger.receipts_total > ledger.receipts.length && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Showing the latest {ledger.receipts.length} of {ledger.receipts_total} receipts; the totals count them all.</p>
      )}

      {permissions.can_record && (open === "new" ? (
        <form onSubmit={submit} noValidate aria-label="Record a commission receipt" aria-busy={busy} className="card" style={{ padding: 14, display: "grid", gap: 12 }}>
          <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 12 }}>
            <div style={grid}>
              <div className="field" style={field}>
                <label htmlFor="cl-amount">Amount</label>
                <input id="cl-amount" type="number" inputMode="decimal" min="0.01" step="0.01" value={values.amount} onChange={set("amount")} />
              </div>
              <div className="field" style={field}>
                <label htmlFor="cl-currency">Currency</label>
                <select id="cl-currency" value={values.currency} onChange={set("currency")}>
                  <option value="">Choose</option>
                  {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="field" style={field}>
                <label htmlFor="cl-date">Date received</label>
                <input id="cl-date" type="date" max={today} value={values.received_on} onChange={set("received_on")} />
              </div>
              <div className="field" style={field}>
                <label htmlFor="cl-reference">Reference</label>
                <input id="cl-reference" maxLength={120} value={values.reference} onChange={set("reference")} placeholder="Remittance or invoice reference" />
              </div>
            </div>
            <div className="field" style={field}>
              <label htmlFor="cl-note">Note</label>
              <textarea id="cl-note" rows={2} maxLength={500} value={values.note} onChange={set("note")} placeholder="e.g. Lump sum for the January intake" />
            </div>
            <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 6 }}>
              <legend style={{ fontWeight: 700 }}>Linked applications (optional)</legend>
              {ledger.applications.length === 0 ? <p className="muted" style={{ margin: 0 }}>No enrolled applications to link.</p> : (
                <ul className="list-clean" style={{ display: "grid", gap: 4 }}>
                  {ledger.applications.map((a) => (
                    <li key={a.id}>
                      <label style={{ display: "inline-flex", gap: 6, alignItems: "center", overflowWrap: "anywhere" }}>
                        <input type="checkbox" checked={linked.includes(a.id)} onChange={(e) => setLinked((ids) => (e.target.checked ? [...ids, a.id] : ids.filter((id) => id !== a.id)))} />
                        {applicationLabel(a)}{a.amount && a.currency ? ` · ${moneyText(a.currency, a.amount)}` : ""}
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </fieldset>
          </fieldset>
          {failure && <p className="form-error" role="alert">{failure}</p>}
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save receipt"}</button>
            <button type="button" className="btn secondary small" onClick={() => show(null)} disabled={busy}>Cancel</button>
          </div>
        </form>
      ) : (
        <div><button id={recordId} type="button" className="btn secondary small" onClick={() => show("new")} disabled={busy}>Record a receipt</button></div>
      ))}
      {failure && open !== "new" && <p className="form-error" role="alert">{failure}</p>}
      {notice && <p className="muted" role="status">{notice}</p>}
    </section>
  );
}

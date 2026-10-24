"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import {
  DEPOSIT_STATUS_LABELS,
  DepositPayload,
  DepositRecord,
  DepositStatus,
  depositReceiptsUrl,
  depositUrl,
  documentDownloadUrl,
  money,
  OfferDocument,
} from "@/lib/applicationOffers";

type Props = { applicationId: string; onChanged: (message: string) => void };

const today = () => new Date().toISOString().slice(0, 10);
const PAID: DepositStatus[] = ["paid_to_university", "paid_via_edusphere"];

// ccrm-025 (DEC-SCOPE-255, D2): the university deposit on an application. An agency deposit paid through EduSphere (AGN-011) is shown
// read-only; otherwise the counselor keeps a manual record in any currency, started from the current offer's deposit.
export default function ApplicationDepositPanel({ applicationId, onChanged }: Props) {
  const [data, setData] = useState<DepositPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  async function load() {
    setLoadError(null);
    const outcome = await sendRequest(depositUrl(applicationId), {});
    if (!outcome.ok) return setLoadError(outcome.message);
    setData(outcome.data as unknown as DepositPayload);
  }

  useEffect(() => {
    load();
  }, [applicationId]); // eslint-disable-line react-hooks/exhaustive-deps -- reload only when the application changes

  if (loadError) {
    return (
      <div className="form-error" role="alert" style={{ marginTop: 8 }}>
        {loadError}{" "}
        <button type="button" className="btn ghost small" onClick={load}>
          Try again
        </button>
      </div>
    );
  }
  if (data === null) return <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>Loading deposit…</p>;

  const agency = data.agency_deposit;
  return (
    <section aria-label="University deposit" style={{ marginTop: 8 }}>
      <h4 style={{ margin: "0 0 4px", fontSize: 14 }}>University deposit</h4>
      {agency ? (
        <p style={{ fontSize: 13, margin: 0 }}>
          Paid by the agency through EduSphere: {money(agency.currency, agency.amount) ?? "no amount"}, status {agency.status.replace(/_/g, " ")}
          {agency.due_date && `, due ${agency.due_date}`}. Read-only here.
        </p>
      ) : editing ? (
        <DepositForm
          applicationId={applicationId}
          data={data}
          onSaved={(message) => {
            setEditing(false);
            onChanged(message);
            load();
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <>
          {data.record ? <RecordView record={data.record} /> : <p className="muted" style={{ fontSize: 13, margin: 0 }}>No deposit recorded yet.</p>}
          <button type="button" className="btn ghost small" style={{ marginTop: 6 }} onClick={() => setEditing(true)}>
            {data.record ? "Update deposit" : "Record deposit"}
          </button>
        </>
      )}
    </section>
  );
}

function RecordView({ record }: { record: DepositRecord }) {
  const [error, setError] = useState<string | null>(null);

  async function openReceipt(document: OfferDocument) {
    setError(null);
    const outcome = await sendRequest(documentDownloadUrl(document.id), {});
    if (!outcome.ok) return setError(outcome.message);
    window.open(String(outcome.data.url), "_blank", "noopener,noreferrer");
  }

  return (
    <div className="card" style={{ padding: 10, fontSize: 13 }}>
      <span className="badge">{record.payment_status_label}</span>
      {record.required && (
        <p style={{ margin: "4px 0 0" }}>
          {money(record.currency, record.amount)}
          {record.due_date && ` · due ${record.due_date}`}
          {record.paid_on && ` · paid ${record.paid_on}`}
        </p>
      )}
      <p className="muted" style={{ margin: "4px 0 0" }}>Updated by {record.updated_by ?? "—"}</p>
      {record.receipt && (
        <button type="button" className="btn ghost small" style={{ marginTop: 6 }} onClick={() => openReceipt(record.receipt as OfferDocument)}>
          Open receipt<span className="visually-hidden"> {record.receipt.name} (opens in a new tab)</span>
        </button>
      )}
      {error && <div className="form-error" role="status">{error}</div>}
    </div>
  );
}

function DepositForm({ applicationId, data, onSaved, onCancel }: { applicationId: string; data: DepositPayload; onSaved: (m: string) => void; onCancel: () => void }) {
  const id = applicationId;
  const start = data.record ?? null;
  const [required, setRequired] = useState(start ? start.required : true);
  const [fields, setFields] = useState({
    amount: start?.amount ?? data.prefill?.amount ?? "",
    currency: start?.currency ?? data.prefill?.currency ?? "",
    due_date: start?.due_date ?? data.prefill?.due_date ?? "",
    paid_on: start?.paid_on ?? "",
  });
  const [status, setStatus] = useState<DepositStatus>(start && start.payment_status !== "not_required" ? start.payment_status : "pending");
  const [receiptId, setReceiptId] = useState(start?.receipt?.id ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a same-tick second submit sends nothing
  const set = (key: keyof typeof fields) => (event: { target: { value: string } }) => setFields((f) => ({ ...f, [key]: event.target.value }));
  const paid = PAID.includes(status);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      let receipt: string | null = receiptId || null;
      if (required && file) {
        const form = new FormData();
        form.set("file", file);
        const uploaded = await sendRequest(depositReceiptsUrl(id), { method: "POST", body: form });
        if (!uploaded.ok) return setError(uploaded.message);
        receipt = String((uploaded.data.document as OfferDocument).id);
      }
      const body = required
        ? {
            required: true,
            amount: fields.amount.trim() || null,
            currency: fields.currency.trim().toUpperCase() || null,
            due_date: fields.due_date || null,
            payment_status: status,
            paid_on: paid ? fields.paid_on || null : null,
            receipt_document_id: receipt,
          }
        : { required: false, payment_status: "not_required" };
      const outcome = await sendJson(depositUrl(id), "PUT", body);
      if (!outcome.ok) return setError(outcome.message);
      onSaved(outcome.data.changed === false ? "This deposit is already recorded." : "Deposit saved.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Record deposit" style={{ marginTop: 4 }}>
      <fieldset className="field">
        <legend>Is a deposit required?</legend>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
          <label>
            <input type="radio" name={`deposit-required-${id}`} checked={required} onChange={() => setRequired(true)} /> Yes
          </label>
          <label>
            <input type="radio" name={`deposit-required-${id}`} checked={!required} onChange={() => setRequired(false)} /> No
          </label>
        </div>
      </fieldset>
      {required && (
        <>
          <div className="form-grid">
            <div className="field">
              <label htmlFor={`deposit-amount-${id}`}>Amount</label>
              <input id={`deposit-amount-${id}`} type="number" min="0.01" step="0.01" inputMode="decimal" required value={fields.amount} onChange={set("amount")} />
            </div>
            <div className="field">
              <label htmlFor={`deposit-currency-${id}`}>Currency</label>
              <input id={`deposit-currency-${id}`} maxLength={3} minLength={3} placeholder="GBP" autoComplete="off" required value={fields.currency} onChange={set("currency")} />
            </div>
            <div className="field">
              <label htmlFor={`deposit-due-${id}`}>Due date (optional)</label>
              <input id={`deposit-due-${id}`} type="date" value={fields.due_date} onChange={set("due_date")} />
            </div>
            <div className="field">
              <label htmlFor={`deposit-status-${id}`}>Payment status</label>
              <select id={`deposit-status-${id}`} value={status} onChange={(e) => setStatus(e.target.value as DepositStatus)}>
                {(Object.keys(DEPOSIT_STATUS_LABELS) as DepositStatus[])
                  .filter((value) => value !== "not_required")
                  .map((value) => (
                    <option key={value} value={value}>
                      {DEPOSIT_STATUS_LABELS[value]}
                    </option>
                  ))}
              </select>
            </div>
            {paid && (
              <div className="field">
                <label htmlFor={`deposit-paid-${id}`}>Paid on</label>
                <input id={`deposit-paid-${id}`} type="date" required max={today()} value={fields.paid_on} onChange={set("paid_on")} />
              </div>
            )}
          </div>
          {data.receipts.length > 0 && (
            <div className="field">
              <label htmlFor={`deposit-receipt-${id}`}>Receipt</label>
              <select id={`deposit-receipt-${id}`} value={receiptId} disabled={file !== null} onChange={(e) => setReceiptId(e.target.value)}>
                <option value="">None</option>
                {data.receipts.map((receipt) => (
                  <option key={receipt.id} value={receipt.id}>
                    {receipt.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="field">
            <label htmlFor={`deposit-file-${id}`}>{data.receipts.length ? "Or upload a receipt (PDF or image, optional)" : "Upload a receipt (PDF or image, optional)"}</label>
            <input id={`deposit-file-${id}`} type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
        </>
      )}
      {error && (
        <div className="form-error" role="status" aria-live="polite">
          {error}
        </div>
      )}
      <div className="actions" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : "Save deposit"}
        </button>
        <button type="button" className="btn ghost small" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

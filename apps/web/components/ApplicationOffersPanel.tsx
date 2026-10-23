"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import {
  APPLICATION_OFFER_TYPE_LABELS,
  ApplicationOffer,
  ApplicationOfferType,
  CLOSE_STATUSES,
  CloseStatus,
  documentDownloadUrl,
  money,
  OFFER_STATUS_LABELS,
  OfferDocument,
  offerLettersUrl,
  offersUrl,
  OffersPayload,
  withdrawUrl,
} from "@/lib/applicationOffers";

type Props = { applicationId: string; onChanged: (message: string) => void };

const NEED_LETTER = "Attach the offer letter: pick an uploaded one or upload the file.";
const CLOSED_MESSAGES: Record<CloseStatus, string> = { withdrawn_by_university: "Offer marked withdrawn by the university.", expired: "Offer marked expired." };
const today = () => new Date().toISOString().slice(0, 10);
const blank = (value: string) => value.trim() || null;

// ccrm-023 (DEC-SCOPE-245): every offer an application received, newest first; record a new one (it supersedes the current one) or
// close the current one (OF4). The server checks every rule and each role's scope again.
export default function ApplicationOffersPanel({ applicationId, onChanged }: Props) {
  const [data, setData] = useState<OffersPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mode, setMode] = useState<"list" | "record" | "close">("list");

  async function load() {
    setLoadError(null);
    const outcome = await sendRequest(offersUrl(applicationId), {});
    if (!outcome.ok) return setLoadError(outcome.message);
    setData(outcome.data as unknown as OffersPayload);
  }

  useEffect(() => {
    load();
  }, [applicationId]); // eslint-disable-line react-hooks/exhaustive-deps -- reload only when the application changes

  function saved(message: string) {
    setMode("list");
    onChanged(message);
    load();
  }

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
  if (data === null) return <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>Loading offers…</p>;

  const current = data.offers.find((o) => o.status === "active");
  return (
    <section aria-label="Offers" style={{ marginTop: 8 }}>
      {data.offers.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>No offer recorded yet.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
          {data.offers.map((offer) => (
            <OfferItem key={offer.id} offer={offer} />
          ))}
        </ul>
      )}
      {mode === "record" && <RecordOfferForm applicationId={applicationId} letters={data.offer_letters} onSaved={saved} onCancel={() => setMode("list")} />}
      {mode === "close" && current && <CloseOfferForm applicationId={applicationId} offer={current} onSaved={saved} onCancel={() => setMode("list")} />}
      {mode === "list" && (
        <div className="actions" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
          <button type="button" className="btn small" onClick={() => setMode("record")}>
            {current ? "Record new offer" : "Record offer"}
          </button>
          {current && (
            <button type="button" className="btn ghost small" onClick={() => setMode("close")}>
              Close offer
            </button>
          )}
        </div>
      )}
    </section>
  );
}

function OfferItem({ offer }: { offer: ApplicationOffer }) {
  const [letterError, setLetterError] = useState<string | null>(null);
  const amounts = (
    [
      ["Tuition", money(offer.currency, offer.tuition_amount)],
      ["Scholarship", money(offer.currency, offer.scholarship_amount)],
      ["Deposit", money(offer.currency, offer.deposit_amount)],
    ] as const
  ).filter(([, value]) => value);

  async function openLetter(document: OfferDocument) {
    setLetterError(null);
    const outcome = await sendRequest(documentDownloadUrl(document.id), {});
    if (!outcome.ok) return setLetterError(outcome.message);
    window.open(String(outcome.data.url), "_blank", "noopener,noreferrer");
  }

  return (
    <li className="card" style={{ padding: 10, fontSize: 13 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        <span className="badge">{OFFER_STATUS_LABELS[offer.status]}</span>
        <strong>{offer.offer_type_label} offer</strong>
      </div>
      <p className="muted" style={{ margin: "4px 0 0" }}>
        Issued {offer.issue_date}
        {offer.offer_deadline && ` · Offer deadline ${offer.offer_deadline}`}
        {offer.deposit_deadline && ` · Deposit due ${offer.deposit_deadline}`}
      </p>
      {amounts.length > 0 && (
        <p style={{ margin: "4px 0 0" }}>
          {amounts.map(([label, value], index) => (
            <span key={label}>
              {index > 0 && " · "}
              {label}: <span>{value}</span>
            </span>
          ))}
        </p>
      )}
      {offer.conditions && <p style={{ margin: "4px 0 0", whiteSpace: "pre-line" }}>Conditions: {offer.conditions}</p>}
      {offer.status_reason && <p style={{ margin: "4px 0 0" }}>Reason: {offer.status_reason}</p>}
      <p className="muted" style={{ margin: "4px 0 0" }}>Recorded by {offer.recorded_by ?? "an earlier record"}</p>
      {offer.document && (
        <button type="button" className="btn ghost small" style={{ marginTop: 6 }} onClick={() => openLetter(offer.document as OfferDocument)}>
          Open letter<span className="visually-hidden"> {offer.document.name} (opens in a new tab)</span>
        </button>
      )}
      {letterError && <div className="form-error" role="status">{letterError}</div>}
    </li>
  );
}

function RecordOfferForm({ applicationId, letters, onSaved, onCancel }: { applicationId: string; letters: OfferDocument[]; onSaved: (m: string) => void; onCancel: () => void }) {
  const id = applicationId;
  const [type, setType] = useState<ApplicationOfferType | "">("");
  const [fields, setFields] = useState({ issue_date: "", offer_deadline: "", conditions: "", currency: "", tuition_amount: "", scholarship_amount: "", deposit_amount: "", deposit_deadline: "" });
  const [documentId, setDocumentId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a same-tick second submit sends nothing
  const set = (key: keyof typeof fields) => (event: { target: { value: string } }) => setFields((f) => ({ ...f, [key]: event.target.value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    if (!documentId && !file) return setError(NEED_LETTER);
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      let letter = documentId;
      if (file) {
        const form = new FormData();
        form.set("file", file);
        const uploaded = await sendRequest(offerLettersUrl(id), { method: "POST", body: form });
        if (!uploaded.ok) return setError(uploaded.message);
        letter = String((uploaded.data.document as OfferDocument).id);
      }
      const outcome = await sendJson(offersUrl(id), "POST", {
        offer_type: type,
        issue_date: fields.issue_date,
        offer_deadline: fields.offer_deadline || null,
        conditions: type === "unconditional" ? null : blank(fields.conditions),
        currency: blank(fields.currency)?.toUpperCase() ?? null,
        tuition_amount: blank(fields.tuition_amount),
        scholarship_amount: blank(fields.scholarship_amount),
        deposit_amount: blank(fields.deposit_amount),
        deposit_deadline: fields.deposit_deadline || null,
        offer_document_id: letter,
      });
      if (!outcome.ok) return setError(outcome.message);
      onSaved(outcome.data.changed === false ? "This offer is already recorded." : "Offer recorded.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Record offer" style={{ marginTop: 8 }}>
      <fieldset className="field">
        <legend>Offer type</legend>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
          {(Object.keys(APPLICATION_OFFER_TYPE_LABELS) as ApplicationOfferType[]).map((value) => (
            <label key={value}>
              <input type="radio" name={`offer-type-${id}`} value={value} required checked={type === value} onChange={() => setType(value)} /> {APPLICATION_OFFER_TYPE_LABELS[value]}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="form-grid">
        <div className="field">
          <label htmlFor={`offer-issue-${id}`}>Issue date</label>
          <input id={`offer-issue-${id}`} type="date" required max={today()} value={fields.issue_date} onChange={set("issue_date")} />
        </div>
        <div className="field">
          <label htmlFor={`offer-deadline-${id}`}>Offer deadline (optional)</label>
          <input id={`offer-deadline-${id}`} type="date" min={fields.issue_date || undefined} value={fields.offer_deadline} onChange={set("offer_deadline")} />
        </div>
      </div>
      {type !== "unconditional" && (
        <div className="field">
          <label htmlFor={`offer-conditions-${id}`}>{type === "conditional" ? "Conditions (required for a conditional offer)" : "Conditions (optional)"}</label>
          <textarea id={`offer-conditions-${id}`} rows={3} maxLength={2000} required={type === "conditional"} value={fields.conditions} onChange={set("conditions")} />
        </div>
      )}
      <div className="form-grid">
        <div className="field">
          <label htmlFor={`offer-currency-${id}`}>Currency</label>
          <input id={`offer-currency-${id}`} maxLength={3} placeholder="GBP" autoComplete="off" aria-describedby={`offer-currency-hint-${id}`} value={fields.currency} onChange={set("currency")} />
          <small id={`offer-currency-hint-${id}`} className="muted">
            Three letters, needed when you enter an amount.
          </small>
        </div>
        <div className="field">
          <label htmlFor={`offer-tuition-${id}`}>Tuition fee</label>
          <input id={`offer-tuition-${id}`} type="number" min="0" step="0.01" inputMode="decimal" value={fields.tuition_amount} onChange={set("tuition_amount")} />
        </div>
        <div className="field">
          <label htmlFor={`offer-scholarship-${id}`}>Scholarship (confirmed only)</label>
          <input id={`offer-scholarship-${id}`} type="number" min="0" step="0.01" inputMode="decimal" value={fields.scholarship_amount} onChange={set("scholarship_amount")} />
        </div>
        <div className="field">
          <label htmlFor={`offer-deposit-${id}`}>Deposit amount</label>
          <input id={`offer-deposit-${id}`} type="number" min="0" step="0.01" inputMode="decimal" value={fields.deposit_amount} onChange={set("deposit_amount")} />
        </div>
        <div className="field">
          <label htmlFor={`offer-deposit-deadline-${id}`}>Deposit deadline</label>
          <input id={`offer-deposit-deadline-${id}`} type="date" min={fields.issue_date || undefined} value={fields.deposit_deadline} onChange={set("deposit_deadline")} />
        </div>
      </div>
      {letters.length > 0 && (
        <div className="field">
          <label htmlFor={`offer-letter-${id}`}>Offer letter</label>
          <select id={`offer-letter-${id}`} value={documentId} disabled={file !== null} onChange={(e) => setDocumentId(e.target.value)}>
            <option value="">Not chosen</option>
            {letters.map((letter) => (
              <option key={letter.id} value={letter.id}>
                {letter.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="field">
        <label htmlFor={`offer-file-${id}`}>{letters.length ? "Or upload a new offer letter (PDF or image)" : "Upload the offer letter (PDF or image)"}</label>
        <input id={`offer-file-${id}`} type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </div>
      {error && (
        <div className="form-error" role="status" aria-live="polite">
          {error}
        </div>
      )}
      <div className="actions" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : "Save offer"}
        </button>
        <button type="button" className="btn ghost small" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function CloseOfferForm({ applicationId, offer, onSaved, onCancel }: { applicationId: string; offer: ApplicationOffer; onSaved: (m: string) => void; onCancel: () => void }) {
  const id = applicationId;
  const [status, setStatus] = useState<CloseStatus>("withdrawn_by_university");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const outcome = await sendJson(withdrawUrl(id, offer.id), "POST", { status, reason: reason.trim() });
      if (!outcome.ok) return setError(outcome.message);
      onSaved(CLOSED_MESSAGES[status]);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Close offer" style={{ marginTop: 8 }}>
      <p className="muted" style={{ fontSize: 13 }}>
        The {offer.offer_type_label.toLowerCase()} offer stays in the history; the application keeps its stage.
      </p>
      <div className="field">
        <label htmlFor={`offer-outcome-${id}`}>Outcome</label>
        <select id={`offer-outcome-${id}`} value={status} onChange={(e) => setStatus(e.target.value as CloseStatus)}>
          {CLOSE_STATUSES.map((value) => (
            <option key={value} value={value}>
              {OFFER_STATUS_LABELS[value]}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`offer-reason-${id}`}>Reason</label>
        <textarea id={`offer-reason-${id}`} rows={2} maxLength={500} required value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      {error && (
        <div className="form-error" role="status" aria-live="polite">
          {error}
        </div>
      )}
      <div className="actions" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : "Confirm"}
        </button>
        <button type="button" className="btn ghost small" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

"use client";
import { type FormEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";

import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson, sendRequest, type SendOutcome } from "@/lib/apiErrors";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";
import { RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import {
  type ApplicationOffer, applicationOfferUrl, isApplicationOffer, LETTER_ACCEPT, LETTER_MAX_BYTES, NOTE_MAX, OFFER_STATUS_LABELS, offerEventText,
  offerOf, offerUrl, type RecOffer, salaryText, START_STATUSES,
} from "@/lib/recruiterOffers";

type Failure = { kind: "session" | "error"; message: string };
type Saved = (offer: RecOffer) => void;

/** One small form's submit: the API's 422s go on their fields; a refusal (409) stays on the form in its words. In-flight guarded. */
function useSubmit(onSaved: Saved) {
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<Failure | null>(null);
  const inFlight = useRef(false); // rec-020 QA-01: a fast double click runs submit twice before `busy` re-renders the button disabled
  async function run(send: () => Promise<SendOutcome>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setFailure(null);
    const result = await send();
    inFlight.current = false;
    setBusy(false);
    if (result.ok) {
      const saved = offerOf(result.data);
      return saved ? onSaved(saved) : setFailure({ kind: "error", message: SAVE_FAILED });
    }
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    const kind = writeFailure(result.status);
    setFailure(kind === "session" ? { kind, message: SESSION_ENDED } : { kind: "error", message: kind === "retry" ? SAVE_FAILED : result.message });
  }
  return { busy, errors, setErrors, failure, setFailure, run };
}

function Problem({ failure }: { failure: Failure | null }) {
  if (!failure) return null;
  return (
    <div role="alert">
      <p className="form-error">{failure.message}</p>
      {failure.kind === "session" && <ReturnToLoginLink loginHref={RECRUITER_SIGN_IN} />}
    </div>
  );
}

function Field({ id, label, error, children }: { id: string; label: string; error?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {error && <p id={`${id}-error`} className="form-error">{error}</p>}
    </div>
  );
}

type Values = { status: string; position: string; compensation: string; currency: string; offered_on: string; joining_date: string };

/** OF4 / OF5: record an offer (with its starting status) or revise one (only changed fields are sent). Typed values are never cleared. */
function OfferForm({ applicationId, offer, suggested, onSaved, onCancel }: {
  applicationId: string; offer?: RecOffer; suggested?: string; onSaved: Saved; onCancel: () => void;
}) {
  const id = useId();
  const [start] = useState<Values>({
    status: offer?.status ?? "offer_pending", position: offer?.position ?? suggested ?? "", compensation: offer?.compensation == null ? "" : String(Number(offer.compensation)),
    currency: offer?.currency ?? "INR", offered_on: offer?.offered_on ?? "", joining_date: offer?.joining_date ?? "",
  });
  const [v, setV] = useState(start);
  const { busy, errors, setErrors, failure, run } = useSubmit(onSaved);
  const fid = (key: string) => `${id}-${key}`;
  const set = (key: keyof Values) => (e: { target: { value: string } }) => setV({ ...v, [key]: e.target.value });
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });

  function body(): Record<string, unknown> {
    const fields: Record<string, unknown> = {
      position: v.position.trim(), compensation: v.compensation.trim() === "" ? null : Number(v.compensation), currency: v.currency.trim().toUpperCase(),
      ...(v.offered_on ? { offered_on: v.offered_on } : {}), joining_date: v.joining_date || null,
    };
    if (!offer) {
      return Object.fromEntries([["status", v.status], ...Object.entries(fields).filter(([key, value]) => value !== null || key === "position")]);
    }
    const stored: Record<string, unknown> = {
      position: offer.position, compensation: offer.compensation == null ? null : Number(offer.compensation), currency: offer.currency,
      offered_on: offer.offered_on, joining_date: offer.joining_date,
    };
    return Object.fromEntries(Object.entries(fields).filter(([key, value]) => value !== stored[key]));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (v.position.trim().length < 2) return setErrors({ position: "Enter the position (at least 2 characters)" });
    const changes = body();
    if (offer && Object.keys(changes).length === 0) return onCancel();
    void run(() => (offer ? sendJson(offerUrl(offer.id), "PATCH", changes) : sendJson(applicationOfferUrl(applicationId), "POST", changes)));
  }

  return (
    <form aria-label={offer ? "Edit offer" : "Record offer"} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))" }}>
        {!offer && (
          <Field id={fid("status")} label="Status" error={errors.status}>
            <select id={fid("status")} value={v.status} onChange={set("status")} {...invalid("status")}>
              {START_STATUSES.map((key) => <option key={key} value={key}>{OFFER_STATUS_LABELS[key]}</option>)}
            </select>
          </Field>
        )}
        <Field id={fid("position")} label="Position (required)" error={errors.position}>
          <input id={fid("position")} autoFocus required aria-required="true" maxLength={160} value={v.position} onChange={set("position")} {...invalid("position")} />
        </Field>
        <Field id={fid("compensation")} label="Salary (per year)" error={errors.compensation}>
          <input id={fid("compensation")} type="number" inputMode="decimal" min="0" step="0.01" value={v.compensation} onChange={set("compensation")} {...invalid("compensation")} />
        </Field>
        <Field id={fid("currency")} label="Currency" error={errors.currency}>
          <input id={fid("currency")} maxLength={3} autoCapitalize="characters" value={v.currency} onChange={set("currency")} {...invalid("currency")} />
        </Field>
        <Field id={fid("offered_on")} label={offer ? "Offer date" : "Offer date (default today)"} error={errors.offered_on}>
          <input id={fid("offered_on")} type="date" value={v.offered_on} onChange={set("offered_on")} {...invalid("offered_on")} />
        </Field>
        <Field id={fid("joining_date")} label="Joining date" error={errors.joining_date}>
          <input id={fid("joining_date")} type="date" value={v.joining_date} onChange={set("joining_date")} {...invalid("joining_date")} />
        </Field>
      </div>
      <Problem failure={failure} />
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save offer"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** OF3: one of the moves the API allows, with an optional note. */
function StatusForm({ offer, onSaved, onCancel }: { offer: RecOffer; onSaved: Saved; onCancel: () => void }) {
  const id = useId();
  const [status, setStatus] = useState("");
  const [note, setNote] = useState("");
  const { busy, errors, setErrors, failure, run } = useSubmit(onSaved);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!status) return setErrors({ status: "Choose a status" });
    void run(() => sendJson(offerUrl(offer.id, "status"), "POST", { status, ...(note.trim() ? { note: note.trim() } : {}) }));
  }
  return (
    <form aria-label="Change offer status" className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <Field id={`${id}-status`} label="New status (required)" error={errors.status}>
        <select id={`${id}-status`} autoFocus required aria-required="true" value={status} onChange={(e) => setStatus(e.target.value)}
          aria-invalid={errors.status ? true : undefined} aria-describedby={errors.status ? `${id}-status-error` : undefined}>
          <option value="">Choose a status</option>
          {offer.allowed_statuses.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
      </Field>
      {status === "declined" && <p className="muted" style={{ margin: 0, fontSize: 13 }}>Declined also moves the candidate to Withdrawn.</p>}
      <Field id={`${id}-note`} label="Note (optional)" error={errors.note}>
        <textarea id={`${id}-note`} rows={2} maxLength={NOTE_MAX} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <Problem failure={failure} />
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save status"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** OF7: the letter (PDF, JPG or PNG; the API judges the type by the bytes). Replacing keeps the old one in the history. */
function LetterUpload({ offer, onSaved }: { offer: RecOffer; onSaved: Saved }) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const { busy, failure, setFailure, run } = useSubmit((saved) => {
    if (input.current) input.current.value = "";
    onSaved(saved);
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    const file = input.current?.files?.[0];
    if (!file) return setFailure({ kind: "error", message: "Choose a PDF, JPG or PNG file first." });
    if (file.size > LETTER_MAX_BYTES) return setFailure({ kind: "error", message: "The letter must be at most 20 MB." });
    const form = new FormData();
    form.append("file", file);
    void run(() => sendRequest(offerUrl(offer.id, "letter"), { method: "PUT", body: form }));
  }
  return (
    <form onSubmit={submit} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
      <div className="field" style={{ flex: "1 1 14rem", marginBottom: 0 }}>
        <label htmlFor={`${id}-file`}>{offer.letter ? "Replace offer letter" : "Upload offer letter"}</label>
        <span id={`${id}-hint`} className="muted" style={{ fontSize: 13 }}>PDF, JPG or PNG, up to 20 MB</span>
        <input id={`${id}-file`} ref={input} type="file" accept={LETTER_ACCEPT} aria-describedby={`${id}-hint`} disabled={busy} />
      </div>
      <button type="submit" className="btn secondary small" disabled={busy}>{busy ? "Uploading…" : "Upload"}</button>
      <div style={{ flexBasis: "100%" }}><Problem failure={failure} /></div>
    </form>
  );
}

function OfferView({ offer: o, candidateName, onChanged }: { offer: RecOffer; candidateName: string; onChanged: (offer: RecOffer, notice: string) => void }) {
  const [mode, setMode] = useState<"view" | "status" | "edit">("view");
  const headingId = useId();
  const salary = salaryText(o.compensation, o.currency);
  const facts = [
    ["Company", o.company.name],
    ["Job", `${o.requirement.title} (${o.requirement.code})`],
    ["Position", o.position ?? "—"],
    salary && ["Salary", salary],
    ["Offer date", formatCalendarDate(o.offered_on)],
    o.joining_date && ["Joining date", formatCalendarDate(o.joining_date)],
  ].filter(Boolean) as [string, string][];
  const done = (text: string) => (next: RecOffer) => {
    setMode("view");
    onChanged(next, text);
  };
  return (
    <section className="action-card" style={{ gap: 6 }} aria-labelledby={headingId}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong id={headingId}>Offer<span className="visually-hidden"> for {candidateName}</span></strong>
        <span className="badge">{o.status_label}</span>
      </div>
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))", gap: "4px 16px", margin: 0 }}>
        {facts.map(([term, value]) => (
          <div key={term}>
            <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
            <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
          </div>
        ))}
      </dl>
      {(o.letter || o.letter_url) && (
        <p style={{ margin: 0, display: "flex", flexWrap: "wrap", gap: 12 }}>
          {o.letter && <a href={offerUrl(o.id, "letter")} download>Download offer letter<span className="muted" style={{ fontSize: 13 }}>{o.letter.name ? ` (${o.letter.name})` : ""}</span></a>}
          {o.letter_url && <a href={o.letter_url} target="_blank" rel="noopener noreferrer">Letter link<span className="visually-hidden"> (opens in a new tab)</span></a>}
        </p>
      )}
      {mode === "view" && (o.allowed_statuses.length > 0 || o.can_edit) && (
        <div className="actions" style={{ flexWrap: "wrap" }}>
          {o.allowed_statuses.length > 0 && <button type="button" className="btn secondary small" onClick={() => setMode("status")}>Change status<span className="visually-hidden"> of the offer</span></button>}
          {o.can_edit && <button type="button" className="btn secondary small" onClick={() => setMode("edit")}>Edit offer</button>}
        </div>
      )}
      {mode === "status" && <StatusForm offer={o} onCancel={() => setMode("view")} onSaved={(next) => done(`Offer for ${candidateName} is now ${next.status_label}.`)(next)} />}
      {mode === "edit" && <OfferForm applicationId={o.application.id} offer={o} onCancel={() => setMode("view")} onSaved={done(`Offer for ${candidateName} revised.`)} />}
      {o.can_upload && mode === "view" && <LetterUpload offer={o} onSaved={done(`Offer letter uploaded for ${candidateName}.`)} />}
      <details>
        <summary>History ({o.history.length})</summary>
        <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 13 }}>
          {[...o.history].reverse().map((h, index) => (
            <li key={`${h.created_at}-${index}`} style={{ overflowWrap: "anywhere" }}>{offerEventText(h, formatSchoolDateTime(h.created_at, true))}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}

/** rec-022 (spec §4): one application's offer on the requirement's candidate row -- the §16 details, the letter and the history, with
 *  the actions the API allows; or "No offer yet." with "+ Record offer" for a Selected candidate (AC1). Every change is reported up,
 *  because Declined moves the application to Withdrawn (OF6). */
export default function RecruiterApplicationOffer({ applicationId, candidateName, onChanged }: {
  applicationId: string; candidateName: string; onChanged: (notice: string) => void;
}) {
  const [data, setData] = useState<ApplicationOffer | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(applicationOfferUrl(applicationId), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => (isApplicationOffer(body) ? setData(body) : setFailed(true)))
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [applicationId, version]);

  const changed = (offer: RecOffer, notice: string) => {
    setAdding(false);
    setData({ offer, can_create: false });
    onChanged(notice);
  };
  if (failed) {
    return (
      <div>
        <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>Unable to load the offer.</p>
        <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
      </div>
    );
  }
  if (data === null) return <p className="muted" role="status" style={{ margin: 0, fontSize: 13 }}>Loading offer…</p>;
  if (data.offer) return <OfferView offer={data.offer} candidateName={candidateName} onChanged={changed} />;
  return (
    <div style={{ display: "grid", gap: 8 }}>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>No offer yet.</p>
      {data.can_create && !adding && (
        <div>
          <button type="button" className="btn secondary small" onClick={() => setAdding(true)}>
            + Record offer<span className="visually-hidden"> for {candidateName}</span>
          </button>
        </div>
      )}
      {adding && (
        <OfferForm applicationId={applicationId} suggested={data.suggested_position} onCancel={() => setAdding(false)}
          onSaved={(offer) => changed(offer, `Offer recorded for ${candidateName}.`)} />
      )}
    </div>
  );
}

"use client";

import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import { isRequestBody } from "@/lib/apiErrors";
import { formatCalendarDate } from "@/lib/formatDate";
import {
  convert, convertBody, entryProblem, failureText, MAX_INSTALLMENTS, money, newIdempotencyKey,
  type ConversionResult, type ConvertEntry, type ConvertOptions,
} from "@/lib/itConversion";
import type { StudentSuggestion } from "@/lib/leadHandover";

type Notice = { text: string; failed: boolean } | null;
const INR = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

/** itc-011: "Convert to IT student" -- one step from a lead to an IT student account (or an existing one), an enrolment in a batch, the
 *  fee (prefilled from the counseling record) with optional installments, and the onboarding checklist (previewed). One Idempotency-Key
 *  per opened form, so a resubmit after a dropped connection never converts twice. The API decides every rule; the entry is kept on any
 *  failure, and a 409 for an existing IT student offers that student (counselor only: `suggestionsUrl`). */
export default function ItConvertForm({ url, suggestionsUrl, onConverted, defaultOpen = false, onCancel }: {
  url: string; suggestionsUrl?: string; onConverted: (result: ConversionResult) => void; defaultOpen?: boolean; onCancel?: () => void;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<ConvertOptions | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [entry, setEntry] = useState<ConvertEntry>({ full_name: "", email: "", phone: "", batch_id: "", fee: "", installments: [] });
  const [feeTouched, setFeeTouched] = useState(false);
  const [matches, setMatches] = useState<StudentSuggestion[] | null>(null);
  const [existing, setExisting] = useState<StudentSuggestion | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const inFlight = useRef(false);
  const key = useRef("");

  async function load() {
    setLoadFailed(false);
    setOptions(null);
    const response = await fetch(url).catch(() => null);
    const data = response?.ok ? ((await response.json().catch(() => null)) as ConvertOptions | null) : null;
    if (!data || !Array.isArray(data.batches)) return setLoadFailed(true);
    const first = data.batches[0];
    const fee = data.prefill.fee ?? first?.fee ?? null;
    setOptions(data);
    setEntry({ full_name: data.prefill.full_name ?? "", email: data.prefill.email ?? "", phone: data.prefill.phone ?? "", batch_id: first?.id ?? "",
               fee: fee === null ? "" : String(fee), installments: [] });
    setFeeTouched(data.prefill.fee !== null);
  }

  function start() {
    key.current = newIdempotencyKey();
    setOpen(true);
    setNotice(null);
    setMatches(null);
    setExisting(null);
    void load();
  }

  useEffect(() => {
    if (defaultOpen) start(); // the admin table opens the form from its own row button
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, on mount
  }, []);

  function cancel() {
    setOpen(false);
    setNotice(null);
    onCancel?.();
  }

  function change(patch: Partial<ConvertEntry>) {
    setEntry((e) => ({ ...e, ...patch }));
    setNotice(null);
  }

  function pickBatch(batchId: string) {
    const batch = options?.batches.find((b) => b.id === batchId);
    change(feeTouched || !batch ? { batch_id: batchId } : { batch_id: batchId, fee: String(batch.fee) }); // the course fee until the counselor sets one
  }

  function setInstallment(index: number, patch: Partial<ConvertEntry["installments"][number]>) {
    change({ installments: entry.installments.map((item, i) => (i === index ? { ...item, ...patch } : item)) });
  }

  async function offerExisting() {
    if (!suggestionsUrl) return;
    const response = await fetch(suggestionsUrl).catch(() => null);
    const data = response?.ok ? ((await response.json().catch(() => null)) as { items?: StudentSuggestion[] } | null) : null;
    setMatches((data?.items ?? []).filter((s) => !s.linked_elsewhere));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    const problem = entryProblem(entry, existing !== null);
    if (problem) return setNotice({ text: problem, failed: true });
    inFlight.current = true;
    setBusy(true);
    const outcome = await convert(url, convertBody(entry, existing?.id ?? null), key.current);
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) {
      const { text, studentExists } = failureText(outcome);
      setNotice({ text, failed: true });
      if (studentExists) void offerExisting();
      return;
    }
    const result = outcome.data as unknown as ConversionResult;
    if (!result.enrollment || !isRequestBody(result.lead)) return setNotice({ text: "Unable to convert the lead.", failed: true });
    setOpen(false);
    onConverted(result);
  }

  if (!open) return <div><button type="button" className="btn small" onClick={start}>Convert to IT student</button></div>;

  const field = (name: "full_name" | "email" | "phone", label: string, type: string, max: number) => (
    <div className="field">
      <label htmlFor={`${id}-${name}`}>{label}</label>
      <input id={`${id}-${name}`} type={type} maxLength={max} autoComplete="off" aria-required={name !== "phone"} value={entry[name]} disabled={busy}
        onChange={(e) => change({ [name]: e.target.value })} />
    </div>
  );
  const batches = options?.batches ?? [];
  const planned = entry.installments.reduce((sum, i) => sum + (money(i.amount) || 0), 0);

  return (
    <form onSubmit={submit} noValidate aria-label="Convert to IT student" style={{ display: "grid", gap: 10, maxWidth: "36rem" }}>
      {!options && !loadFailed && <p className="muted" role="status" style={{ margin: 0 }}>Loading batches…</p>}
      {loadFailed && (
        <p className="form-error" role="alert" style={{ margin: 0 }}>
          Couldn&apos;t load the batches. <button type="button" className="btn secondary small" onClick={() => void load()}>Try again</button>
        </p>
      )}
      {options && (
        <>
          {existing ? (
            <p style={{ margin: 0, overflowWrap: "anywhere" }}>
              Enrolling the existing student <strong>{existing.full_name}</strong> ({existing.email}).{" "}
              <button type="button" className="btn secondary small" disabled={busy} onClick={() => { setExisting(null); setNotice(null); }}>Create a new account instead</button>
            </p>
          ) : (
            <fieldset style={{ display: "grid", gap: 8, border: 0, padding: 0, margin: 0 }}>
              <legend style={{ fontWeight: 600, padding: 0 }}>Student account</legend>
              {field("full_name", "Full name", "text", 160)}
              {field("email", "Email", "email", 255)}
              {field("phone", "Phone (optional)", "tel", 40)}
            </fieldset>
          )}
          {matches !== null && !existing && (
            matches.length ? (
              <div role="group" aria-label="Existing IT students" style={{ display: "grid", gap: 6 }}>
                {matches.map((s) => (
                  <div key={s.id} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                    <span style={{ overflowWrap: "anywhere" }}>{s.full_name} · {s.email}</span>
                    <button type="button" className="btn secondary small" onClick={() => { setExisting(s); setNotice(null); }}>Enrol {s.full_name}</button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>No free matching student was found; change the email or mobile.</p>
            )
          )}
          <div className="field">
            <label htmlFor={`${id}-batch`}>Batch</label>
            {batches.length ? (
              <select id={`${id}-batch`} value={entry.batch_id} disabled={busy} aria-required onChange={(e) => pickBatch(e.target.value)}>
                {batches.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.recommended ? "★ " : ""}{b.program} — {b.name} (starts {formatCalendarDate(b.start_date)}, {b.available} seat{b.available === 1 ? "" : "s"} left)
                  </option>
                ))}
              </select>
            ) : (
              <p className="muted" style={{ margin: 0 }}>No open batch has a seat left. Ask the IT Admin to open one.</p>
            )}
            {options.prefill.recommended_course && <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>★ Recommended in counseling: {options.prefill.recommended_course}</p>}
          </div>
          <div className="field">
            <label htmlFor={`${id}-fee`}>Fee (INR)</label>
            <input id={`${id}-fee`} type="number" inputMode="decimal" min={0} step="0.01" value={entry.fee} disabled={busy} aria-required
              aria-describedby={`${id}-fee-hint`} onChange={(e) => { setFeeTouched(true); change({ fee: e.target.value }); }} />
            <p id={`${id}-fee-hint`} className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
              {options.prefill.fee !== null ? "Prefilled from the fee quoted in counseling." : "Prefilled from the course fee."} Enter 0 for a full scholarship.
            </p>
          </div>
          <fieldset style={{ display: "grid", gap: 8, border: 0, padding: 0, margin: 0 }}>
            <legend style={{ fontWeight: 600, padding: 0 }}>Installments (optional)</legend>
            {entry.installments.map((item, index) => (
              <div key={index} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "end" }}>
                <div className="field" style={{ flex: "1 1 8rem", minWidth: 0 }}>
                  <label htmlFor={`${id}-amount-${index}`}>Installment {index + 1} amount</label>
                  <input id={`${id}-amount-${index}`} type="number" inputMode="decimal" min={0} step="0.01" value={item.amount} disabled={busy}
                    onChange={(e) => setInstallment(index, { amount: e.target.value })} />
                </div>
                <div className="field" style={{ flex: "1 1 9rem", minWidth: 0 }}>
                  <label htmlFor={`${id}-due-${index}`}>Installment {index + 1} due date</label>
                  <input id={`${id}-due-${index}`} type="date" value={item.due_date} disabled={busy} onChange={(e) => setInstallment(index, { due_date: e.target.value })} />
                </div>
                <button type="button" className="btn secondary small" disabled={busy} aria-label={`Remove installment ${index + 1}`}
                  onClick={() => change({ installments: entry.installments.filter((_, i) => i !== index) })}>Remove</button>
              </div>
            ))}
            {entry.installments.length > 0 && (
              <p className="muted" style={{ margin: 0, fontSize: 13 }} aria-live="polite">Planned {INR.format(planned)} of {INR.format(money(entry.fee) || 0)}</p>
            )}
            {entry.installments.length < MAX_INSTALLMENTS && (
              <div><button type="button" className="btn secondary small" disabled={busy} onClick={() => change({ installments: [...entry.installments, { amount: "", due_date: "" }] })}>Add installment</button></div>
            )}
            {!entry.installments.length && <p className="muted" style={{ margin: 0, fontSize: 13 }}>Without installments the whole fee is one bill.</p>}
          </fieldset>
          <div>
            <p style={{ margin: 0, fontWeight: 600 }}>Onboarding checklist</p>
            {options.checklist.length ? (
              <ul style={{ margin: "4px 0 0", paddingLeft: 20 }}>{options.checklist.map((label) => <li key={label}>{label}</li>)}</ul>
            ) : (
              <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>No checklist items are set up.</p>
            )}
          </div>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            {existing ? "Enrols the student" : "Creates the student's account, emails a set-password link, enrols them"} in the batch, sets up the fee and the
            checklist, and moves the lead to Application/Enrollment. It becomes Converted once the student accepts the enrolment agreement.
          </p>
        </>
      )}
      {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0, fontSize: 13 }}>{notice.text}</p>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button type="submit" className="btn small" disabled={busy || !options || !batches.length}>{busy ? "Converting…" : existing ? "Enrol existing student" : "Convert and enrol"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={cancel}>Cancel</button>
      </div>
    </form>
  );
}

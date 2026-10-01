"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import SearchableSelect from "@/components/SearchableSelect";
import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { type FundingRecord, type FundingStatus, nextStatuses, STATUS_LABEL, SUPPORT_TYPE_LABEL, TEXT_LIMITS } from "@/lib/fundingRecords";

type Student = { id: string; full_name: string; school_name: string };

const CASES = "/api/v1/school/funding-records";

// ENH-020 (spec §6): open or update one funding support case. The stage select only offers moves the API accepts, so a refused save
// usually means someone else changed the case -- shown with a Reload action. Closing asks for a reason and puts focus on it.
// `onDone` receives the saved case (the API's response) so the host can announce the result and place focus: an edit form unmounts
// on save, so its own message would never be read (final review I2).
export default function FundingRecordForm({ students, record, onDone, onCancel }: { students: Student[]; record?: FundingRecord; onDone: (saved: FundingRecord) => void; onCancel: () => void }) {
  const router = useRouter();
  const editing = Boolean(record);
  const [supportType, setSupportType] = useState("");
  const [status, setStatus] = useState<FundingStatus | "">(record?.status ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const [stale, setStale] = useState(false);
  const inFlight = useRef(false);
  const reasonRef = useRef<HTMLInputElement>(null);
  const prefix = record ? `funding-${record.id}` : "funding-new";
  const closing = status === "closed";

  useEffect(() => {
    if (closing) reasonRef.current?.focus();
  }, [closing]);

  function onKey(event: KeyboardEvent) {
    if (event.key === "Escape") onCancel();
  }

  function text(form: FormData, key: string): string {
    return String(form.get(key) ?? "").trim();
  }

  function payload(form: FormData): Record<string, unknown> {
    const details = { provider_name: text(form, "provider_name") || null, amount_text: text(form, "amount_text") || null, notes: String(form.get("notes") ?? "") };
    if (!record) return { school_student_id: form.get("school_student_id"), support_type: supportType, ...details };
    const body: Record<string, unknown> = { expected_status: record.status };
    if (status && status !== record.status) body.status = status;
    if (closing) body.closure_reason = text(form, "closure_reason");
    return { ...body, ...details };
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || inFlight.current) return;
    const formElement = event.currentTarget;
    const body = payload(new FormData(formElement));
    inFlight.current = true;
    setBusy(true);
    setMessage(null);
    setStale(false);
    // Raw fetch (the CareerRecordForm pattern) rather than sendJson: a 409 on an edit needs its status code to offer Reload.
    let response: Response | null;
    try {
      response = await fetch(record ? `${CASES}/${record.id}` : CASES, { method: record ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } catch {
      response = null;
    }
    const data = response ? await response.json().catch(() => null) : null;
    inFlight.current = false;
    setBusy(false);
    if (!response?.ok) {
      setStale(editing && response?.status === 409);
      const failure = !response ? NOT_COMPLETED : response.status >= 500 ? "Something went wrong on our side. Please try again; your entry is kept." : detailMessage(data?.detail);
      setMessage({ text: failure, failed: true });
      return;
    }
    setMessage({ text: "Case saved.", failed: false });
    if (!editing) {
      formElement.reset();
      setSupportType("");
    }
    router.refresh();
    onDone(data as FundingRecord);
  }

  return (
    <form className="form" onSubmit={submit} onKeyDown={onKey} onChange={() => { if (message && !message.failed) setMessage(null); }}>
      <fieldset className="form-busy-wrap" disabled={busy}>
        <div className="form-grid">
          {!record && (
            <>
              <SearchableSelect id={`${prefix}-student`} label="Student" name="school_student_id" required noun="student" options={students.map((s) => ({ id: s.id, label: s.full_name, detail: s.school_name }))} />
              <div className="field">
                <label htmlFor={`${prefix}-type`}>Support type</label>
                <select id={`${prefix}-type`} name="support_type" required value={supportType} onChange={(e) => setSupportType(e.target.value)}>
                  <option value="" disabled>Select type</option>
                  {Object.entries(SUPPORT_TYPE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
            </>
          )}
          {record && (
            <div className="field">
              <label htmlFor={`${prefix}-stage`}>Stage</label>
              <select id={`${prefix}-stage`} value={status} onChange={(e) => setStatus(e.target.value as FundingStatus)} aria-describedby={`${prefix}-stage-help`}>
                {[record.status, ...nextStatuses(record.status)].map((s) => <option key={s} value={s}>{s === record.status ? `${STATUS_LABEL[s]} (current)` : STATUS_LABEL[s]}</option>)}
              </select>
              <p id={`${prefix}-stage-help`} className="field-help muted">Required → Counselling → Documents → Application → Approved → Completed, one stage at a time. Close a case that will not go ahead.</p>
            </div>
          )}
          {closing && (
            <div className="field">
              <label htmlFor={`${prefix}-reason`}>Reason for closing</label>
              <input id={`${prefix}-reason`} ref={reasonRef} name="closure_reason" required maxLength={TEXT_LIMITS.closure_reason} aria-describedby={`${prefix}-reason-help`} />
              <p id={`${prefix}-reason-help`} className="field-help muted">For example: loan not approved, family withdrew. A closed case cannot be reopened.</p>
            </div>
          )}
          <div className="field">
            <label htmlFor={`${prefix}-provider`}>Provider or institution (optional)</label>
            <input id={`${prefix}-provider`} name="provider_name" maxLength={TEXT_LIMITS.provider_name} defaultValue={record?.provider_name ?? ""} />
          </div>
          <div className="field">
            <label htmlFor={`${prefix}-amount`}>Amount (optional)</label>
            <input id={`${prefix}-amount`} name="amount_text" maxLength={TEXT_LIMITS.amount_text} defaultValue={record?.amount_text ?? ""} aria-describedby={`${prefix}-amount-help`} />
            <p id={`${prefix}-amount-help`} className="field-help muted">As written by the provider, e.g. ₹5,00,000 or 50% of tuition.</p>
          </div>
          <div className="field full">
            <label htmlFor={`${prefix}-notes`}>Notes</label>
            <textarea id={`${prefix}-notes`} name="notes" maxLength={TEXT_LIMITS.notes} defaultValue={record?.notes ?? ""} />
          </div>
        </div>
        <div className="actions">
          <button className="btn" id={`${prefix}-save`} aria-busy={busy}>{busy ? "Saving…" : record ? "Save changes" : "Add case"}</button>
          {record && <button type="button" className="btn secondary" onClick={onCancel}>Cancel</button>}
        </div>
      </fieldset>
      {message && <FormMessage message={message} />}
      {stale && <button type="button" className="btn secondary small" onClick={() => { router.refresh(); onCancel(); }}>Discard my changes and reload</button>}
    </form>
  );
}

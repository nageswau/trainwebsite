"use client";
import { type ChangeEvent, type FormEvent, useId, useState } from "react";

import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { istInputToIso, isoToIstInput, nowIstInput } from "@/lib/bdmAppointments";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { companyFollowUpsUrl, followUpUrl, isRecFollowUp, NOTES_MAX, REASONS, type RecFollowUp } from "@/lib/recruiterFollowUps";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

type Values = { due: string; reason: string; contact_id: string; notes: string };
export type ContactOption = { id: string; name: string };

// rec-024 (spec §4; FU5, FU6): add a follow-up to a company, or reschedule / edit an open one. Times are entered and shown in IST. The
// contact picker shows only when `contacts` is given (the company page); elsewhere the stored contact is left as it is. The API decides
// every rule (future time, the cap, the links); this form places its answers on the fields and never clears typed text.
export default function RecruiterFollowUpForm({ companyId, contacts, followUp, onSaved, onCancel }: {
  companyId: string; contacts?: ContactOption[]; followUp?: RecFollowUp; onSaved: (followUp: RecFollowUp) => void; onCancel: () => void;
}) {
  const id = useId();
  const [start] = useState<Values>({
    due: followUp ? isoToIstInput(followUp.due_at) : "", reason: followUp?.reason ?? "", contact_id: followUp?.contact?.id ?? "",
    notes: followUp?.notes ?? "",
  });
  const [v, setV] = useState(start);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [now] = useState(nowIstInput);
  const dirty = (Object.keys(start) as (keyof Values)[]).some((key) => v[key] !== start[key]);
  useLeaveGuard(!busy && dirty, "Discard this follow-up?");
  // A stored contact that has since been deactivated is still shown, so editing other fields never drops it.
  const contactOptions = contacts && followUp?.contact && !contacts.some((c) => c.id === followUp.contact?.id) ? [...contacts, followUp.contact] : contacts;
  const fid = (key: string) => `${id}-${key}`;
  const set = (key: keyof Values) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setV({ ...v, [key]: e.target.value });
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;

  function send(): Promise<SendOutcome> | null {
    const body: Record<string, string | null> = {
      due_at: istInputToIso(v.due), reason: v.reason, notes: v.notes.trim() || null, ...(contacts ? { contact_id: v.contact_id || null } : {}),
    };
    if (!followUp) return sendJson(companyFollowUpsUrl(companyId), "POST", body);
    const changes: Record<string, string | null> = {};
    if (v.due !== start.due) changes.due_at = body.due_at;
    if (v.reason !== start.reason) changes.reason = body.reason;
    if (contacts && v.contact_id !== start.contact_id) changes.contact_id = body.contact_id;
    if (body.notes !== (followUp.notes ?? null)) changes.notes = body.notes;
    return Object.keys(changes).length ? sendJson(followUpUrl(followUp.id), "PATCH", changes) : null;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const missing: Record<string, string> = {};
    if (!v.due) missing.due_at = "Choose a due date and time";
    if (!v.reason) missing.reason = "Choose a reason";
    if (Object.keys(missing).length) return setErrors(missing);
    const request = send();
    if (!request) return onCancel();
    setBusy(true);
    setErrors({});
    setFailure(null);
    setSessionEnded(false);
    const result = await request;
    setBusy(false);
    if (result.ok) return isRecFollowUp(result.data) ? onSaved(result.data) : setFailure(SAVE_FAILED);
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    const kind = writeFailure(result.status);
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message); // a refusal (the cap, a link, archived) in the server's words
  }

  return (
    <form aria-label={followUp ? "Reschedule follow-up" : "Add follow-up"} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
        <div className="field">
          <label htmlFor={fid("due_at")}>Due date and time (IST, required)</label>
          <input id={fid("due_at")} type="datetime-local" autoFocus required aria-required="true" min={now} value={v.due} onChange={set("due")} {...invalid("due_at")} />
          {error("due_at")}
        </div>
        <div className="field">
          <label htmlFor={fid("reason")}>Reason (required)</label>
          <select id={fid("reason")} required aria-required="true" value={v.reason} onChange={set("reason")} {...invalid("reason")}>
            <option value="">Select a reason</option>
            {REASONS.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select>
          {error("reason")}
        </div>
        {contactOptions && (
          <div className="field">
            <label htmlFor={fid("contact_id")}>Contact</label>
            <select id={fid("contact_id")} value={v.contact_id} onChange={set("contact_id")} {...invalid("contact_id")}>
              <option value="">No specific contact</option>
              {contactOptions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            {error("contact_id")}
          </div>
        )}
      </div>
      <div className="field">
        <label htmlFor={fid("notes")}>Notes</label>
        <textarea id={fid("notes")} rows={3} maxLength={NOTES_MAX} value={v.notes} onChange={set("notes")} aria-invalid={errors.notes ? true : undefined}
          aria-describedby={errors.notes ? `${fid("notes")}-count ${fid("notes")}-error` : `${fid("notes")}-count`} />
        <p id={`${fid("notes")}-count`} className="muted" style={{ margin: 0 }}>{v.notes.length}/{NOTES_MAX}</p>
        {error("notes")}
      </div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {sessionEnded && (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref={RECRUITER_SIGN_IN} />
        </div>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : followUp ? "Save changes" : "Add follow-up"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

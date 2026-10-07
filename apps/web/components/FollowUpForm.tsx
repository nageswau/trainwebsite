"use client";
import { type ChangeEvent, type FormEvent, useId, useState } from "react";

import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { istInputToIso, isoToIstInput, nowIstInput } from "@/lib/bdmAppointments";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { TELECALLER_SIGN_IN } from "@/lib/navigation";
import {
  ACTION_MAX, NOTES_MAX, REASONS, canMoveToFollowUp, createFollowUpUrl, followUpUrl, isFollowUp, type FollowUp,
} from "@/lib/telecallerFollowUps";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

type Values = { due: string; reason: string; next_action: string; notes: string };

// tel-011 (spec §4; F5, F6): add a follow-up to a lead, or reschedule / edit an open one. Times are entered and shown in IST. The API
// decides every rule (future time, closed lead, the cap); this form places its answers on the fields and never clears typed text.
export default function FollowUpForm({ leadId, leadStage, followUp, onSaved, onCancel }: {
  leadId: string; leadStage: string; followUp?: FollowUp; onSaved: (followUp: FollowUp) => void; onCancel: () => void;
}) {
  const id = useId();
  const [start] = useState<Values>({
    due: followUp ? isoToIstInput(followUp.due_at) : "", reason: followUp?.reason ?? "", next_action: followUp?.next_action ?? "",
    notes: followUp?.notes ?? "",
  });
  const [v, setV] = useState(start);
  const [move, setMove] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [now] = useState(nowIstInput);
  const dirty = (Object.keys(start) as (keyof Values)[]).some((key) => v[key] !== start[key]);
  useLeaveGuard(!busy && dirty, "Discard this follow-up?");
  const offerMove = !followUp && canMoveToFollowUp(leadStage);
  const fid = (key: string) => `${id}-${key}`;
  const set = (key: keyof Values) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setV({ ...v, [key]: e.target.value });
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;

  function send(): Promise<SendOutcome> | null {
    const body = { due_at: istInputToIso(v.due), reason: v.reason, next_action: v.next_action.trim() || null, notes: v.notes.trim() || null };
    if (!followUp) return sendJson(createFollowUpUrl(leadId), "POST", { ...body, move_to_follow_up: offerMove && move });
    const changes: Record<string, string | null> = {};
    if (v.due !== start.due) changes.due_at = body.due_at;
    if (v.reason !== start.reason) changes.reason = body.reason;
    if (body.next_action !== (followUp.next_action ?? null)) changes.next_action = body.next_action;
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
    if (result.ok) return isFollowUp(result.data) ? onSaved(result.data) : setFailure(SAVE_FAILED);
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    const kind = writeFailure(result.status);
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message); // a refusal (closed lead, the cap, handed over) in the server's words
  }

  const label = followUp ? "Reschedule follow-up" : "Add follow-up";
  return (
    <form aria-label={label} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
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
      </div>
      <div className="field">
        <label htmlFor={fid("next_action")}>Next action</label>
        <input id={fid("next_action")} maxLength={ACTION_MAX} placeholder="e.g. Call today at 4:00 PM" value={v.next_action} onChange={set("next_action")} {...invalid("next_action")} />
        {error("next_action")}
      </div>
      <div className="field">
        <label htmlFor={fid("notes")}>Notes</label>
        <textarea id={fid("notes")} rows={3} maxLength={NOTES_MAX} value={v.notes} onChange={set("notes")} aria-invalid={errors.notes ? true : undefined}
          aria-describedby={errors.notes ? `${fid("notes")}-count ${fid("notes")}-error` : `${fid("notes")}-count`} />
        <p id={`${fid("notes")}-count`} className="muted" style={{ margin: 0 }}>{v.notes.length}/{NOTES_MAX}</p>
        {error("notes")}
      </div>
      {offerMove && (
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
          <input type="checkbox" checked={move} onChange={(e) => setMove(e.target.checked)} /> Also move the lead to Follow-up
        </label>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {sessionEnded && (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref={TELECALLER_SIGN_IN} />
        </div>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : followUp ? "Save changes" : "Add follow-up"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

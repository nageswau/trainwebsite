"use client";
import { type ChangeEvent, type FormEvent, useId, useRef, useState } from "react";

import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { istInputToIso, isoToIstInput, nowIstInput } from "@/lib/bdmAppointments";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { TELECALLER_SIGN_IN } from "@/lib/navigation";
import {
  CALL_TYPES, OUTCOMES, REMARKS_MAX, callUrl, closesAs, createCallUrl, isLeadCall, isLogCallResult, needsFollowUp, toSeconds, type LeadCall,
  type LogCallResult,
} from "@/lib/telecallerCalls";
import { ACTION_MAX, REASONS, canMoveToFollowUp } from "@/lib/telecallerFollowUps";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

type Values = { when: string; minutes: string; seconds: string; call_type: string; outcome: string; remarks: string; due: string; reason: string;
  next_action: string };
// QA-01: a fieldset legend reads like the `.field label` text beside it
const LEGEND = { fontWeight: 800, fontSize: 13, padding: 0, marginBottom: 7 } as const;
const BACKDATE_DAYS = 7; // D6: the API's bound; the picker's min is a hint only

function earliestInput(): string {
  const date = new Date(Date.now() - BACKDATE_DAYS * 86_400_000);
  return `${isoToIstInput(date.toISOString()).slice(0, 10)}T00:00`;
}

// tel-010 (spec §5; CL3, CL4, D3-D7): log a call on a lead, or edit one of today's. Times are entered in IST. The outcome sets what the
// form asks for -- a next follow-up when the outcome needs one (D4), none when it closes the lead -- and the API decides every rule; its
// answers land on the fields and typed text is never cleared. Editing never offers the outcome (CL4: delete and log again).
export default function CallLogForm({ leadId, leadStage, call, onLogged, onEdited, onCancel }: {
  leadId: string; leadStage: string; call?: LeadCall; onLogged?: (result: LogCallResult) => void; onEdited?: (call: LeadCall) => void;
  onCancel: () => void;
}) {
  const id = useId();
  const [start] = useState<Values>(() => ({
    when: call ? isoToIstInput(call.occurred_at) : nowIstInput(), minutes: call ? String(Math.floor(call.duration_seconds / 60)) : "",
    seconds: call ? String(call.duration_seconds % 60) : "", call_type: call?.call_type ?? "outgoing", outcome: call?.outcome ?? "",
    remarks: call?.remarks ?? "", due: "", reason: "", next_action: "",
  }));
  const [v, setV] = useState(start);
  const [addFollowUp, setAddFollowUp] = useState(false);
  const [move, setMove] = useState(false);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [limits] = useState(() => ({ max: nowIstInput(), min: call ? `${nowIstInput().slice(0, 10)}T00:00` : earliestInput() }));
  const dirty = (Object.keys(start) as (keyof Values)[]).some((key) => v[key] !== start[key]);
  useLeaveGuard(!busy && dirty, "Discard this call?");

  const closing = closesAs(v.outcome);
  const required = needsFollowUp(v.outcome);
  const withFollowUp = !call && !!v.outcome && !closing && (required || addFollowUp);
  const fid = (key: string) => `${id}-${key}`;
  const set = (key: keyof Values) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setV({ ...v, [key]: e.target.value });
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;

  function check(seconds: number | null): Record<string, string> {
    const missing: Record<string, string> = {};
    if (!v.when) missing.occurred_at = "Choose the call date and time";
    if (seconds === null) missing.duration_seconds = "Enter whole minutes and seconds (0–59), up to 4 hours";
    if (!call && !v.outcome) missing.outcome = "Choose an outcome";
    if (v.outcome === "duplicate_lead" && !v.remarks.trim()) missing.remarks = "Add remarks naming the other lead";
    if (withFollowUp && !v.due) missing.due_at = "Choose a due date and time";
    if (withFollowUp && !v.reason) missing.reason = "Choose a reason";
    return missing;
  }

  function send(seconds: number): Promise<SendOutcome> | null {
    const remarks = v.remarks.trim() || null;
    if (!call) {
      const nextFollowUp = withFollowUp ? {
        due_at: istInputToIso(v.due), reason: v.reason, next_action: v.next_action.trim() || null, move_to_follow_up: canMoveToFollowUp(leadStage) && move,
      } : null;
      return sendJson(createCallUrl(leadId), "POST", {
        occurred_at: istInputToIso(v.when), duration_seconds: seconds, call_type: v.call_type, outcome: v.outcome, remarks, next_follow_up: nextFollowUp,
      });
    }
    const changes: Record<string, string | number | null> = {};
    if (v.when !== start.when) changes.occurred_at = istInputToIso(v.when);
    if (seconds !== call.duration_seconds) changes.duration_seconds = seconds;
    if (v.call_type !== call.call_type) changes.call_type = v.call_type;
    if (remarks !== (call.remarks ?? null)) changes.remarks = remarks;
    return Object.keys(changes).length ? sendJson(callUrl(call.id), "PATCH", changes) : null;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const seconds = toSeconds(v.minutes, v.seconds);
    const missing = check(seconds);
    if (Object.keys(missing).length || seconds === null) return setErrors(missing);
    if (inFlight.current) return; // QA-02: Enter submits even while Save is disabled; a call is not idempotent
    const request = send(seconds);
    if (!request) return onCancel();
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setFailure(null);
    setSessionEnded(false);
    const result = await request;
    inFlight.current = false;
    setBusy(false);
    if (result.ok) {
      if (!call && isLogCallResult(result.data)) return onLogged?.(result.data);
      if (call && isLeadCall(result.data)) return onEdited?.(result.data);
      return setFailure(SAVE_FAILED);
    }
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    const kind = writeFailure(result.status);
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message); // a refusal (closed lead, handed over, the cap) in the server's words
  }

  const label = call ? "Edit call" : "Log call";
  const grid = { display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" } as const;
  return (
    <form aria-label={label} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="form-grid" style={grid}>
        {!call && (
          <div className="field">
            <label htmlFor={fid("outcome")}>Outcome (required)</label>
            <select id={fid("outcome")} autoFocus required aria-required="true" value={v.outcome} onChange={set("outcome")} {...invalid("outcome")}>
              <option value="">Select an outcome</option>
              <optgroup label="Connected">
                {OUTCOMES.filter((o) => o.connected).map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
              </optgroup>
              <optgroup label="Not connected">
                {OUTCOMES.filter((o) => !o.connected).map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
              </optgroup>
            </select>
            {error("outcome")}
          </div>
        )}
        <div className="field">
          <label htmlFor={fid("occurred_at")}>Call date and time (IST)</label>
          <input id={fid("occurred_at")} type="datetime-local" required aria-required="true" min={limits.min} max={limits.max} value={v.when}
            onChange={set("when")} {...invalid("occurred_at")} />
          {error("occurred_at")}
        </div>
        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }} aria-describedby={errors.duration_seconds ? `${fid("duration_seconds")}-error` : undefined}>
          <legend style={LEGEND}>Duration</legend>
          <div style={{ display: "flex", gap: 8 }}>
            <label style={{ display: "grid", gap: 2, flex: 1, fontWeight: 400 }}>
              <span className="muted" style={{ fontSize: 13 }}>Minutes</span>
              <input type="number" inputMode="numeric" min={0} max={240} step={1} placeholder="0" value={v.minutes} onChange={set("minutes")}
                aria-invalid={errors.duration_seconds ? true : undefined} />
            </label>
            <label style={{ display: "grid", gap: 2, flex: 1, fontWeight: 400 }}>
              <span className="muted" style={{ fontSize: 13 }}>Seconds</span>
              <input type="number" inputMode="numeric" min={0} max={59} step={1} placeholder="0" value={v.seconds} onChange={set("seconds")}
                aria-invalid={errors.duration_seconds ? true : undefined} />
            </label>
          </div>
          {error("duration_seconds")}
        </fieldset>
        <div className="field">
          <label htmlFor={fid("call_type")}>Call type</label>
          <select id={fid("call_type")} value={v.call_type} onChange={set("call_type")} {...invalid("call_type")}>
            {CALL_TYPES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
          {error("call_type")}
        </div>
      </div>
      {closing && <p className="form-message" role="note" style={{ margin: "4px 0 8px" }}>This outcome closes the lead as {closing}. Its open follow-ups are cancelled.</p>}
      <div className="field">
        <label htmlFor={fid("remarks")}>Remarks{v.outcome === "duplicate_lead" ? " (required: name the other lead)" : ""}</label>
        <textarea id={fid("remarks")} rows={3} maxLength={REMARKS_MAX} value={v.remarks} onChange={set("remarks")} aria-invalid={errors.remarks ? true : undefined}
          aria-describedby={errors.remarks ? `${fid("remarks")}-count ${fid("remarks")}-error` : `${fid("remarks")}-count`} />
        <p id={`${fid("remarks")}-count`} className="muted" style={{ margin: 0 }}>{v.remarks.length}/{REMARKS_MAX}</p>
        {error("remarks")}
      </div>
      {!call && v.outcome && !closing && !required && (
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
          <input type="checkbox" checked={addFollowUp} onChange={(e) => setAddFollowUp(e.target.checked)} /> Add a next follow-up
        </label>
      )}
      {withFollowUp && (
        <fieldset style={{ border: 0, padding: 0, margin: "0 0 8px" }}>
          <legend style={{ ...LEGEND, fontSize: 14, marginBottom: 8 }}>Next follow-up{required ? " (required for this outcome)" : ""}</legend>
          {error("next_follow_up")}
          <div className="form-grid" style={grid}>
            <div className="field">
              <label htmlFor={fid("due_at")}>Follow-up due (IST, required)</label>
              <input id={fid("due_at")} type="datetime-local" required aria-required="true" min={limits.max} value={v.due} onChange={set("due")} {...invalid("due_at")} />
              {error("due_at")}
            </div>
            <div className="field">
              <label htmlFor={fid("reason")}>Follow-up reason</label>
              <select id={fid("reason")} required aria-required="true" value={v.reason} onChange={set("reason")} {...invalid("reason")}>
                <option value="">Select a reason</option>
                {REASONS.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
              </select>
              {error("reason")}
            </div>
          </div>
          <div className="field">
            <label htmlFor={fid("next_action")}>Next action</label>
            <input id={fid("next_action")} maxLength={ACTION_MAX} placeholder="e.g. Call today at 4:00 PM" value={v.next_action} onChange={set("next_action")}
              {...invalid("next_action")} />
            {error("next_action")}
          </div>
          {canMoveToFollowUp(leadStage) && (
            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={move} onChange={(e) => setMove(e.target.checked)} /> Also move the lead to Follow-up
            </label>
          )}
        </fieldset>
      )}
      {!withFollowUp && error("next_follow_up")}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {sessionEnded && (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref={TELECALLER_SIGN_IN} />
        </div>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : call ? "Save changes" : "Save call"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

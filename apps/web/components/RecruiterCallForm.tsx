"use client";
import { type ChangeEvent, type FormEvent, useEffect, useId, useRef, useState } from "react";

import type { ContactOption } from "@/components/RecruiterFollowUpForm";
import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { istInputToIso, isoToIstInput, nowIstInput } from "@/lib/bdmAppointments";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import {
  type CallParty, CALLS_URL, callUrl, DIRECTIONS, isLogCallResult, isRecCall, type LogCallResult, NEXT_ACTION_MAX, NOTES_MAX, OBJECTION_NOTES_MAX, OBJECTIONS,
  OUTCOMES, type RecCall,
} from "@/lib/recruiterCalls";
import { RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { NOTES_MAX as FOLLOW_UP_NOTES_MAX, REASONS } from "@/lib/recruiterFollowUps";
import { REQUIREMENTS_URL } from "@/lib/recruiterRequirements";
import { toSeconds } from "@/lib/telecallerCalls";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

type Values = { contact_id: string; outcome: string; when: string; direction: string; minutes: string; seconds: string; notes: string; due: string;
  reason: string; fu_notes: string; job_id: string; objection_notes: string; next_action: string };
const LEGEND = { fontWeight: 800, fontSize: 13, padding: 0, marginBottom: 7 } as const; // reads like the `.field label` beside it (tel-010 QA-01)
const BACKDATE_DAYS = 7; // CA5: the API's bound; the picker's min is a hint only
const GRID = { display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))", alignItems: "start" } as const; // QA-01: a select is not stretched to the duration row

function earliestInput(): string {
  return `${isoToIstInput(new Date(Date.now() - BACKDATE_DAYS * 86_400_000).toISOString()).slice(0, 10)}T00:00`;
}

/** The follow-up's own notes error (`body.next_follow_up.notes`) lands on its field, not on the call's Notes. */
function followUpNotesOnTheirField(detail: unknown): unknown {
  if (!Array.isArray(detail)) return detail;
  return (detail as { loc?: unknown[] }[]).map((item) =>
    item.loc?.includes("next_follow_up") && item.loc[item.loc.length - 1] === "notes" ? { ...item, loc: [...item.loc.slice(0, -1), "fu_notes"] } : item);
}

// rec-025 (spec §4; CA2-CA8): log a call on a contact (picked from the company's active contacts) or a candidate, or edit one of today's.
// Times are entered in IST; duration is optional. A contact call may add the next follow-up (rec-024's reasons); a candidate call never
// does (CA6). Editing never offers the outcome or the party (CA4: delete and log again). The API decides every rule; its answers land on
// the fields and typed text is never cleared.
export default function RecruiterCallForm({ party, contacts = [], call, onLogged, onEdited, onCancel }: {
  party: CallParty; contacts?: ContactOption[]; call?: RecCall; onLogged?: (result: LogCallResult) => void; onEdited?: (call: RecCall) => void;
  onCancel: () => void;
}) {
  const id = useId();
  const [start] = useState<Values>(() => ({
    contact_id: "", outcome: "", when: call ? isoToIstInput(call.occurred_at) : nowIstInput(), direction: call?.direction ?? "outgoing",
    minutes: call?.duration_seconds != null ? String(Math.floor(call.duration_seconds / 60)) : "",
    seconds: call?.duration_seconds != null ? String(call.duration_seconds % 60) : "", notes: call?.notes ?? "", due: "", reason: "", fu_notes: "",
    job_id: call?.requirement?.id ?? "", objection_notes: call?.objection_notes ?? "", next_action: call?.next_action ?? "",
  }));
  const [startObjections] = useState<string[]>(() => call?.objections ?? []);
  const [objections, setObjections] = useState(startObjections);
  const [requirements, setRequirements] = useState<{ id: string; label: string }[]>([]);
  const [v, setV] = useState(start);
  const [addFollowUp, setAddFollowUp] = useState(false);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [limits] = useState(() => ({ max: nowIstInput(), min: call ? `${nowIstInput().slice(0, 10)}T00:00` : earliestInput() }));
  const dirty = (Object.keys(start) as (keyof Values)[]).some((key) => v[key] !== start[key]) || objections.join() !== startObjections.join();
  useLeaveGuard(!busy && dirty, "Discard this call?");

  const contactCall = party.kind === "contact";
  const companyId = party.kind === "contact" ? party.companyId : null;

  useEffect(() => {
    // pob-007 A4: the requirement discussed is one of the company's (a contact call only)
    if (!companyId) return;
    const controller = new AbortController();
    fetch(`${REQUIREMENTS_URL}?${new URLSearchParams({ company_id: companyId, limit: "100" })}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((page: { items: { id: string; code: string; title: string }[] }) =>
        setRequirements(page.items.map((j) => ({ id: j.id, label: `${j.code} — ${j.title}` }))))
      .catch(() => undefined); // the picker stays at "None": a requirement is optional
    return () => controller.abort();
  }, [companyId]);
  const stored = call?.requirement;
  const requirementOptions = stored && !requirements.some((r) => r.id === stored.id) ? [...requirements, { id: stored.id, label: `${stored.code} — ${stored.title}` }] : requirements;
  const toggle = (key: string) => setObjections((list) => (list.includes(key) ? list.filter((k) => k !== key) : [...list, key]));
  const withFollowUp = !call && contactCall && addFollowUp;
  const fid = (key: string) => `${id}-${key}`;
  const set = (key: keyof Values) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setV({ ...v, [key]: e.target.value });
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;

  /** Blank minutes and seconds mean "not recorded" (CA8); anything else must be a whole duration in range. */
  const blankDuration = !v.minutes.trim() && !v.seconds.trim();
  const seconds = blankDuration ? null : toSeconds(v.minutes, v.seconds);

  function check(): Record<string, string> {
    const missing: Record<string, string> = {};
    if (!call && contactCall && !v.contact_id) missing.contact_id = "Choose a contact";
    if (!call && !v.outcome) missing.outcome = "Choose an outcome";
    if (!v.when) missing.occurred_at = "Choose the call date and time";
    if (!blankDuration && seconds === null) missing.duration_seconds = "Enter whole minutes and seconds (0–59), up to 4 hours";
    if (withFollowUp && !v.due) missing.due_at = "Choose a due date and time";
    if (withFollowUp && !v.reason) missing.reason = "Choose a reason";
    return missing;
  }

  function send(): Promise<SendOutcome> | null {
    const notes = v.notes.trim() || null;
    const ordered = OBJECTIONS.map((o) => o.key as string).filter((k) => objections.includes(k));
    const details = { // pob-007 A4
      ...(contactCall ? { job_id: v.job_id || null } : {}), objections: ordered.length ? ordered : null,
      objection_notes: v.objection_notes.trim() || null, next_action: v.next_action.trim() || null,
    };
    if (!call) {
      return sendJson(CALLS_URL, "POST", {
        ...(party.kind === "contact" ? { contact_id: v.contact_id } : { candidate_id: party.candidateId }), ...details,
        outcome: v.outcome, occurred_at: istInputToIso(v.when), direction: v.direction, duration_seconds: seconds, notes,
        next_follow_up: withFollowUp ? { due_at: istInputToIso(v.due), reason: v.reason, notes: v.fu_notes.trim() || null } : null,
      });
    }
    const changes: Record<string, string | string[] | number | null> = {};
    if (v.when !== start.when) changes.occurred_at = istInputToIso(v.when);
    if (seconds !== call.duration_seconds) changes.duration_seconds = seconds;
    if (v.direction !== call.direction) changes.direction = v.direction;
    if (notes !== (call.notes ?? null)) changes.notes = notes;
    if (contactCall && v.job_id !== start.job_id) changes.job_id = v.job_id || null;
    if (ordered.join() !== (call.objections ?? []).join()) changes.objections = details.objections;
    if (details.objection_notes !== (call.objection_notes ?? null)) changes.objection_notes = details.objection_notes;
    if (details.next_action !== (call.next_action ?? null)) changes.next_action = details.next_action;
    return Object.keys(changes).length ? sendJson(callUrl(call.id), "PATCH", changes) : null;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const missing = check();
    if (Object.keys(missing).length) return setErrors(missing);
    if (inFlight.current) return; // Enter submits even while Save is disabled; a call is not idempotent
    const request = send();
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
      if (call && isRecCall(result.data)) return onEdited?.(result.data);
      return setFailure(SAVE_FAILED);
    }
    const placed = fieldErrors(followUpNotesOnTheirField(result.detail));
    if (Object.keys(placed).length) return setErrors(placed);
    const kind = writeFailure(result.status);
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message); // a refusal (archived, inactive contact, the cap) in the server's words
  }

  const label = call ? "Edit call" : "Log call";
  return (
    <form aria-label={label} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="form-grid" style={GRID}>
        {!call && contactCall && (
          <div className="field">
            <label htmlFor={fid("contact_id")}>Contact (required)</label>
            <select id={fid("contact_id")} autoFocus required aria-required="true" value={v.contact_id} onChange={set("contact_id")} {...invalid("contact_id")}>
              <option value="">Select a contact</option>
              {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            {error("contact_id")}
          </div>
        )}
        {!call && (
          <div className="field">
            <label htmlFor={fid("outcome")}>Outcome (required)</label>
            <select id={fid("outcome")} autoFocus={!contactCall} required aria-required="true" value={v.outcome} onChange={set("outcome")} {...invalid("outcome")}>
              <option value="">Select an outcome</option>
              <optgroup label="Connected">{OUTCOMES.filter((o) => o.connected).map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}</optgroup>
              <optgroup label="Not connected">{OUTCOMES.filter((o) => !o.connected).map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}</optgroup>
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
        <div className="field">
          <label htmlFor={fid("direction")}>Direction</label>
          <select id={fid("direction")} value={v.direction} onChange={set("direction")} {...invalid("direction")}>
            {DIRECTIONS.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
          </select>
          {error("direction")}
        </div>
        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }} aria-describedby={errors.duration_seconds ? `${fid("duration_seconds")}-error` : undefined}>
          <legend style={LEGEND}>Duration (optional)</legend>
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
      </div>
      <div className="field">
        <label htmlFor={fid("notes")}>Notes</label>
        <textarea id={fid("notes")} rows={3} maxLength={NOTES_MAX} value={v.notes} onChange={set("notes")} aria-invalid={errors.notes ? true : undefined}
          aria-describedby={errors.notes ? `${fid("notes")}-count ${fid("notes")}-error` : `${fid("notes")}-count`} />
        <p id={`${fid("notes")}-count`} className="muted" style={{ margin: 0 }}>{v.notes.length}/{NOTES_MAX}</p>
        {error("notes")}
      </div>
      {contactCall && (
        <div className="field">
          <label htmlFor={fid("job_id")}>Requirement discussed</label>
          <select id={fid("job_id")} value={v.job_id} onChange={set("job_id")} {...invalid("job_id")}>
            <option value="">None</option>
            {requirementOptions.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
          {error("job_id")}
        </div>
      )}
      <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }} aria-describedby={errors.objections ? `${fid("objections")}-error` : undefined}>
        <legend style={LEGEND}>Objections</legend>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 16px" }}>
          {OBJECTIONS.map((o) => (
            <label key={o.key} style={{ display: "flex", gap: 6, alignItems: "center", fontWeight: 400 }}>
              <input type="checkbox" checked={objections.includes(o.key)} onChange={() => toggle(o.key)} /> {o.label}
            </label>
          ))}
        </div>
        {error("objections")}
      </fieldset>
      <div className="form-grid" style={GRID}>
        <div className="field">
          <label htmlFor={fid("objection_notes")}>Objection details</label>
          <input id={fid("objection_notes")} maxLength={OBJECTION_NOTES_MAX} value={v.objection_notes} onChange={set("objection_notes")} {...invalid("objection_notes")} />
          {error("objection_notes")}
        </div>
        <div className="field">
          <label htmlFor={fid("next_action")}>Next action</label>
          <input id={fid("next_action")} maxLength={NEXT_ACTION_MAX} value={v.next_action} onChange={set("next_action")} {...invalid("next_action")} />
          {error("next_action")}
        </div>
      </div>
      {!call && contactCall && (
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
          <input type="checkbox" checked={addFollowUp} onChange={(e) => setAddFollowUp(e.target.checked)} /> Add a next follow-up
        </label>
      )}
      {withFollowUp && (
        <fieldset style={{ border: 0, padding: 0, margin: "0 0 8px" }}>
          <legend style={{ ...LEGEND, fontSize: 14, marginBottom: 8 }}>Next follow-up</legend>
          {error("next_follow_up")}
          <div className="form-grid" style={GRID}>
            <div className="field">
              <label htmlFor={fid("due_at")}>Follow-up due (IST, required)</label>
              <input id={fid("due_at")} type="datetime-local" required aria-required="true" min={limits.max} value={v.due} onChange={set("due")} {...invalid("due_at")} />
              {error("due_at")}
            </div>
            <div className="field">
              <label htmlFor={fid("reason")}>Follow-up reason (required)</label>
              <select id={fid("reason")} required aria-required="true" value={v.reason} onChange={set("reason")} {...invalid("reason")}>
                <option value="">Select a reason</option>
                {REASONS.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
              </select>
              {error("reason")}
            </div>
          </div>
          <div className="field">
            <label htmlFor={fid("fu_notes")}>Follow-up notes</label>
            <input id={fid("fu_notes")} maxLength={FOLLOW_UP_NOTES_MAX} value={v.fu_notes} onChange={set("fu_notes")} {...invalid("fu_notes")} />
            {error("fu_notes")}
          </div>
        </fieldset>
      )}
      {!withFollowUp && error("next_follow_up")}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {sessionEnded && (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref={RECRUITER_SIGN_IN} />
        </div>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : call ? "Save changes" : "Save call"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

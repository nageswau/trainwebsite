"use client";
import { type ChangeEvent, type FormEvent, useId, useRef, useState } from "react";

import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson } from "@/lib/apiErrors";
import { istInputToIso, isoToIstInput, nowIstInput } from "@/lib/bdmAppointments";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { CALLS_URL } from "@/lib/partnershipComms";
import { DIRECTIONS, NOTES_MAX, OUTCOMES, telHref } from "@/lib/recruiterCalls";
import { toSeconds } from "@/lib/telecallerCalls";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

export type CallContact = { id: string; name: string; phone: string | null };
type Values = { contact_id: string; outcome: string; when: string; direction: string; minutes: string; seconds: string; notes: string; follow_up: string };
const LEGEND = { fontWeight: 800, fontSize: 13, padding: 0, marginBottom: 7 } as const; // reads like the `.field label` beside it
const GRID = { display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))", alignItems: "start" } as const;
const BACKDATE_DAYS = 7; // UC1 (rec-025 CA5): the API's bound; the picker's min is a hint only
const SIGN_IN = "/overseas/login";

// upc-012 (UC1, AC3): log a call with one of the university's contacts -- outcome, time (IST), direction, optional duration, notes and an
// optional next follow-up date. The chosen contact's phone is offered as a tel: link. Calls are permanent (no edit). The API decides
// every rule; its answers land on the fields and typed text is never cleared.
export default function UniversityCallForm({ contacts, onLogged, onCancel }: { contacts: CallContact[]; onLogged: () => void; onCancel: () => void }) {
  const id = useId();
  const [start] = useState<Values>(() => ({ contact_id: "", outcome: "", when: nowIstInput(), direction: "outgoing", minutes: "", seconds: "", notes: "", follow_up: "" }));
  const [v, setV] = useState(start);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [limits] = useState(() => {
    const now = nowIstInput();
    return { max: now, min: `${isoToIstInput(new Date(Date.now() - BACKDATE_DAYS * 86_400_000).toISOString()).slice(0, 10)}T00:00`, today: now.slice(0, 10) };
  });
  useLeaveGuard(!busy && (Object.keys(start) as (keyof Values)[]).some((key) => v[key] !== start[key]), "Discard this call?");

  const contact = contacts.find((c) => c.id === v.contact_id);
  const dial = telHref(contact?.phone);
  const fid = (key: string) => `${id}-${key}`;
  const set = (key: keyof Values) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setV({ ...v, [key]: e.target.value });
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;
  const blankDuration = !v.minutes.trim() && !v.seconds.trim(); // "not recorded"
  const seconds = blankDuration ? null : toSeconds(v.minutes, v.seconds);

  function check(): Record<string, string> {
    const missing: Record<string, string> = {};
    if (!v.contact_id) missing.contact_id = "Choose a contact";
    if (!v.outcome) missing.outcome = "Choose an outcome";
    if (!v.when) missing.occurred_at = "Choose the call date and time";
    if (!blankDuration && seconds === null) missing.duration_seconds = "Enter whole minutes and seconds (0–59), up to 4 hours";
    return missing;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const missing = check();
    if (Object.keys(missing).length) return setErrors(missing);
    if (inFlight.current) return; // Enter submits even while Save is disabled; a call is not idempotent
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setFailure(null);
    setSessionEnded(false);
    const result = await sendJson(CALLS_URL, "POST", {
      contact_id: v.contact_id, outcome: v.outcome, occurred_at: istInputToIso(v.when), direction: v.direction, duration_seconds: seconds,
      notes: v.notes.trim() || null, next_follow_up_on: v.follow_up || null,
    });
    inFlight.current = false;
    setBusy(false);
    if (result.ok) return onLogged();
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    const kind = writeFailure(result.status);
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message); // a refusal (scope, inactive university, the cap) in the server's words
  }

  return (
    <form aria-label="Log call" className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="form-grid" style={GRID}>
        <div className="field">
          <label htmlFor={fid("contact_id")}>Contact (required)</label>
          <select id={fid("contact_id")} autoFocus required aria-required="true" value={v.contact_id} onChange={set("contact_id")} {...invalid("contact_id")}>
            <option value="">Select a contact</option>
            {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          {error("contact_id")}
          {contact && dial && <a href={dial} style={{ fontSize: 13 }}>Call {contact.name} ({contact.phone})</a>}
        </div>
        <div className="field">
          <label htmlFor={fid("outcome")}>Outcome (required)</label>
          <select id={fid("outcome")} required aria-required="true" value={v.outcome} onChange={set("outcome")} {...invalid("outcome")}>
            <option value="">Select an outcome</option>
            <optgroup label="Connected">{OUTCOMES.filter((o) => o.connected).map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}</optgroup>
            <optgroup label="Not connected">{OUTCOMES.filter((o) => !o.connected).map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}</optgroup>
          </select>
          {error("outcome")}
        </div>
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
        <div className="field">
          <label htmlFor={fid("next_follow_up_on")}>Next follow-up (optional)</label>
          <input id={fid("next_follow_up_on")} type="date" min={limits.today} value={v.follow_up} onChange={set("follow_up")} {...invalid("next_follow_up_on")} />
          {error("next_follow_up_on")}
        </div>
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
          <ReturnToLoginLink loginHref={SIGN_IN} />
        </div>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save call"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

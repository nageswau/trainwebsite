"use client";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import { sendJson, type Page } from "@/lib/apiErrors";
import { istInputToIso, nowIstInput } from "@/lib/bdmAppointments";
import { SAVE_FAILED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { MEETING_MODES, NOTES_MAX, isLeadMeeting, meetingsUrl, type LeadMeeting } from "@/lib/leadMeetings";
import { getPage } from "@/lib/telecallerCatalogue";

const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;
type Values = { when: string; mode: string; notes: string };

/** ccrm-004 (DEC-SCOPE-259 LG3): record a meeting -- when (IST), how, notes. The API's answers land on the fields; typed text is kept. */
function MeetingForm({ leadId, onSaved, onCancel }: { leadId: string; onSaved: () => void; onCancel: () => void }) {
  const id = useId();
  const [v, setV] = useState<Values>(() => ({ when: nowIstInput(), mode: MEETING_MODES[0], notes: "" }));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // not idempotent: Enter while saving must not record twice
  const fid = (key: string) => `${id}-${key}`;
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const missing: Record<string, string> = {};
    if (!v.when) missing.occurred_at = "Choose the meeting date and time";
    if (!v.notes.trim()) missing.notes = "Add what was discussed";
    if (Object.keys(missing).length) return setErrors(missing);
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setFailure(null);
    const result = await sendJson(meetingsUrl(leadId), "POST", { occurred_at: istInputToIso(v.when), mode: v.mode, notes: v.notes.trim() });
    inFlight.current = false;
    setBusy(false);
    if (result.ok) return isLeadMeeting(result.data) ? onSaved() : setFailure(SAVE_FAILED);
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    setFailure(writeFailure(result.status) === "retry" ? SAVE_FAILED : result.message);
  }

  return (
    <form aria-label="Record meeting" className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
        <div className="field">
          <label htmlFor={fid("occurred_at")}>Meeting date and time (IST)</label>
          <input id={fid("occurred_at")} type="datetime-local" required aria-required="true" max={nowIstInput()} value={v.when} disabled={busy}
            onChange={(e) => setV({ ...v, when: e.target.value })} {...invalid("occurred_at")} />
          {error("occurred_at")}
        </div>
        <div className="field">
          <label htmlFor={fid("mode")}>Mode</label>
          <select id={fid("mode")} value={v.mode} disabled={busy} onChange={(e) => setV({ ...v, mode: e.target.value })} {...invalid("mode")}>
            {MEETING_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          {error("mode")}
        </div>
      </div>
      <div className="field">
        <label htmlFor={fid("notes")}>Notes (required)</label>
        <textarea id={fid("notes")} rows={3} maxLength={NOTES_MAX} aria-required="true" value={v.notes} disabled={busy} autoFocus
          onChange={(e) => setV({ ...v, notes: e.target.value })} aria-invalid={errors.notes ? true : undefined}
          aria-describedby={errors.notes ? `${fid("notes")}-count ${fid("notes")}-error` : `${fid("notes")}-count`} />
        <p id={`${fid("notes")}-count`} className="muted" style={{ margin: 0 }}>{v.notes.length}/{NOTES_MAX}</p>
        {error("notes")}
      </div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save meeting"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** ccrm-004 (LG3): the lead's meetings, newest first, with Record meeting while `canWrite` (lead not closed). Append-only. */
export default function LeadMeetings({ leadId, canWrite, onChanged }: { leadId: string; canWrite: boolean; onChanged?: () => void }) {
  const [data, setData] = useState<Page<LeadMeeting> | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<LeadMeeting>(meetingsUrl(leadId, true), controller.signal).then(setData).catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [leadId, version]);

  return (
    <section aria-labelledby="lead-meetings-heading">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3 id="lead-meetings-heading" style={{ margin: 0 }}>Meetings</h3>
        {canWrite && !adding && <button type="button" className="btn secondary small" onClick={() => { setAdding(true); setNotice(null); }}>Record meeting</button>}
      </div>
      <div role="status" aria-live="polite">{notice && <p className="form-message" style={{ margin: "6px 0 0", fontSize: 13 }}>{notice}</p>}</div>
      {adding && canWrite && (
        <MeetingForm leadId={leadId} onCancel={() => setAdding(false)} onSaved={() => { setAdding(false); setNotice("Meeting recorded."); reload(); onChanged?.(); }} />
      )}
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the meetings.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status" style={{ fontSize: 13 }}>Loading meetings…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>No meetings recorded yet.</p>
      ) : (
        <ul aria-label="Meetings" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
          {data.items.map((m) => (
            <li key={m.id} className="action-card" style={{ listStyle: "none", gap: 6 }}>
              <strong>{m.mode} meeting</strong>
              <p className="muted" style={{ margin: 0 }}>{formatSchoolDateTime(m.occurred_at, true)} · {m.author.full_name}</p>
              <p style={{ ...TEXT, margin: 0 }}>{m.notes}</p>
            </li>
          ))}
        </ul>
      )}
      {data && data.total > data.items.length && <p className="muted" style={{ fontSize: 13 }}>Showing the latest {data.items.length} of {data.total} meetings.</p>}
    </section>
  );
}

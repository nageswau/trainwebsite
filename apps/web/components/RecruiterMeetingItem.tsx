"use client";
import Link from "next/link";
import { type FormEvent, useId, useState } from "react";

import BdmAppointmentReasonForm from "@/components/BdmAppointmentReasonForm";
import RecruiterMeetingForm, { type ContactOption } from "@/components/RecruiterMeetingForm";
import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { istInputToIso, nowIstInput } from "@/lib/bdmAppointments";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { COMPANIES_PATH, RECRUITER_SIGN_IN, safeLink } from "@/lib/recruiterCompanies";
import { reasonLabel, REASONS } from "@/lib/recruiterFollowUps";
import {
  COMMERCIAL_NOTES_MAX, isRecMeeting, meetingTypeLabel, meetingUrl, NEXT_ACTION_MAX, OUTCOME_MAX, ROWS_MAX, TIMEFRAMES, timeframeLabel, type HistoryEvent,
  type RecMeeting,
} from "@/lib/recruiterMeetings";

const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;
const LEGEND = { fontWeight: 800, fontSize: 13, padding: 0, marginBottom: 4 } as const;
const ROW = { display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))", alignItems: "end" } as const;
type Failure = { kind: "changed" | "session" | "error"; message: string };

/** One request's failure, sorted the way every rec-024/028 action handles it. */
function failureOf(result: Extract<SendOutcome, { ok: false }>): Failure {
  const kind = writeFailure(result.status);
  if (kind === "changed") return { kind, message: result.message };
  if (kind === "session") return { kind, message: SESSION_ENDED };
  return { kind: "error", message: kind === "retry" ? SAVE_FAILED : result.message };
}

/** pob-007: a 422 on an action item or forecast row (`body.action_items.1.due_at`) lands on that row's field. */
function outcomeErrors(detail: unknown): Record<string, string> {
  if (!Array.isArray(detail)) return {};
  const out: Record<string, string> = {};
  for (const item of detail as { loc?: unknown[] }[]) {
    const loc = item.loc ?? [];
    const at = loc.findIndex((part) => part === "action_items" || part === "hiring_forecast");
    const [msg] = Object.values(fieldErrors([item]));
    const key = at < 0 ? String(loc[loc.length - 1] ?? "") : `${loc[at] === "action_items" ? "items" : "forecast"}.${loc.slice(at + 1).join(".")}`;
    if (key && msg && !out[key]) out[key] = msg;
  }
  return out;
}

/** MT7: the outcome (required) and an optional next action -- with a due time (IST) and a reason it becomes a follow-up (AC2). */
function OutcomeForm({ meeting, onSaved, onRefused, onCancel }: {
  meeting: RecMeeting; onSaved: (m: RecMeeting) => void; onRefused: (message: string) => void; onCancel: () => void;
}) {
  const id = useId();
  const [v, setV] = useState({ outcome: "", next_action: "", due: "", reason: "", commercial_notes: "" });
  // pob-007 A5/A6: forecast rows and action items, each added and removed by the recruiter
  const [forecast, setForecast] = useState<{ role: string; count: string; timeframe: string }[]>([]);
  const [items, setItems] = useState<{ action: string; due: string; reason: string }[]>([]);
  const setRow = <T,>(list: T[], set: (rows: T[]) => void, i: number, patch: Partial<T>) => set(list.map((row, j) => (j === i ? { ...row, ...patch } : row)));
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<Failure | null>(null);
  const [now] = useState(nowIstInput);
  const fid = (key: string) => `${id}-${key}`;
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;
  const hasNext = v.next_action.trim() !== "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    const missing: Record<string, string> = {};
    if (!v.outcome.trim()) missing.outcome = "Describe the outcome";
    if (hasNext && !v.due) missing.next_action_due_at = "Choose when the next action is due";
    if (hasNext && !v.reason) missing.next_action_reason = "Choose a follow-up reason";
    forecast.forEach((row, i) => {
      if (!row.role.trim()) missing[`forecast.${i}.role`] = "Enter the role";
      if (!/^\d+$/.test(row.count) || Number(row.count) < 1 || Number(row.count) > 10000) missing[`forecast.${i}.count`] = "Enter a count from 1 to 10000";
      if (!row.timeframe) missing[`forecast.${i}.timeframe`] = "Choose a timeframe";
    });
    items.forEach((item, i) => {
      if (!item.action.trim()) missing[`items.${i}.action`] = "Describe the action";
      if (!item.due) missing[`items.${i}.due_at`] = "Choose when it is due";
      if (!item.reason) missing[`items.${i}.reason`] = "Choose a follow-up reason";
    });
    if (Object.keys(missing).length) return setErrors(missing);
    setBusy(true);
    setErrors({});
    setFailure(null);
    const result = await sendJson(meetingUrl(meeting.id, "outcome"), "POST", {
      outcome: v.outcome.trim(), ...(hasNext ? { next_action: v.next_action.trim(), next_action_due_at: istInputToIso(v.due), next_action_reason: v.reason } : {}),
      ...(forecast.length ? { hiring_forecast: forecast.map((row) => ({ role: row.role.trim(), count: Number(row.count), timeframe: row.timeframe })) } : {}),
      ...(items.length ? { action_items: items.map((item) => ({ action: item.action.trim(), due_at: istInputToIso(item.due), reason: item.reason })) } : {}),
      ...(meeting.commercial_notes_visible && v.commercial_notes.trim() ? { commercial_notes: v.commercial_notes.trim() } : {}),
    });
    setBusy(false);
    if (result.ok) return isRecMeeting(result.data) ? onSaved(result.data) : setFailure({ kind: "error", message: SAVE_FAILED });
    const placed = outcomeErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    const f = failureOf(result);
    if (f.kind === "changed" && result.status !== 409) return onRefused(f.message);
    setFailure(f); // 409 (the follow-up cap, or done meanwhile) and 422 (not started) stay on the form in the server's words
  }

  return (
    <form aria-label="Record outcome" className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="field">
        <label htmlFor={fid("outcome")}>Outcome (required)</label>
        <textarea id={fid("outcome")} autoFocus rows={3} maxLength={OUTCOME_MAX} required aria-required="true" value={v.outcome}
          onChange={(e) => setV({ ...v, outcome: e.target.value })} {...invalid("outcome")} />
        {error("outcome")}
      </div>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
        <div className="field">
          <label htmlFor={fid("next_action")}>Next action</label>
          <input id={fid("next_action")} maxLength={NEXT_ACTION_MAX} value={v.next_action} onChange={(e) => setV({ ...v, next_action: e.target.value })} {...invalid("next_action")} />
          {error("next_action")}
        </div>
        {hasNext && (
          <>
            <div className="field">
              <label htmlFor={fid("next_action_due_at")}>Follow-up due (IST, required)</label>
              <input id={fid("next_action_due_at")} type="datetime-local" min={now} required aria-required="true" value={v.due}
                onChange={(e) => setV({ ...v, due: e.target.value })} {...invalid("next_action_due_at")} />
              {error("next_action_due_at")}
            </div>
            <div className="field">
              <label htmlFor={fid("next_action_reason")}>Follow-up reason (required)</label>
              <select id={fid("next_action_reason")} required aria-required="true" value={v.reason} onChange={(e) => setV({ ...v, reason: e.target.value })} {...invalid("next_action_reason")}>
                <option value="">Select a reason</option>
                {REASONS.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
              </select>
              {error("next_action_reason")}
            </div>
          </>
        )}
      </div>
      {hasNext && <p className="muted" style={{ margin: 0, fontSize: 13 }}>The next action is added to the company&apos;s follow-ups.</p>}
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 6 }}>
        <legend style={LEGEND}>Hiring forecast</legend>
        {forecast.map((row, i) => (
          <div key={i} role="group" aria-label={`Forecast row ${i + 1}`} style={ROW}>
            <div className="field">
              <label htmlFor={fid(`forecast.${i}.role`)}>Role</label>
              <input id={fid(`forecast.${i}.role`)} maxLength={120} value={row.role} onChange={(e) => setRow(forecast, setForecast, i, { role: e.target.value })} {...invalid(`forecast.${i}.role`)} />
              {error(`forecast.${i}.role`)}
            </div>
            <div className="field">
              <label htmlFor={fid(`forecast.${i}.count`)}>Count</label>
              <input id={fid(`forecast.${i}.count`)} type="number" inputMode="numeric" min={1} max={10000} value={row.count}
                onChange={(e) => setRow(forecast, setForecast, i, { count: e.target.value })} {...invalid(`forecast.${i}.count`)} />
              {error(`forecast.${i}.count`)}
            </div>
            <div className="field">
              <label htmlFor={fid(`forecast.${i}.timeframe`)}>Timeframe</label>
              <select id={fid(`forecast.${i}.timeframe`)} value={row.timeframe} onChange={(e) => setRow(forecast, setForecast, i, { timeframe: e.target.value })} {...invalid(`forecast.${i}.timeframe`)}>
                <option value="">Select a timeframe</option>
                {TIMEFRAMES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
              </select>
              {error(`forecast.${i}.timeframe`)}
            </div>
            <button type="button" className="btn secondary small" onClick={() => setForecast(forecast.filter((_, j) => j !== i))}>
              Remove<span className="visually-hidden"> forecast row {i + 1}</span>
            </button>
          </div>
        ))}
        {forecast.length < ROWS_MAX && (
          <div><button type="button" className="btn secondary small" onClick={() => setForecast([...forecast, { role: "", count: "", timeframe: "" }])}>Add forecast row</button></div>
        )}
      </fieldset>
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 6 }}>
        <legend style={LEGEND}>Action items</legend>
        {items.map((item, i) => (
          <div key={i} role="group" aria-label={`Action item ${i + 1}`} style={ROW}>
            <div className="field">
              <label htmlFor={fid(`items.${i}.action`)}>Action</label>
              <input id={fid(`items.${i}.action`)} maxLength={NEXT_ACTION_MAX} value={item.action} onChange={(e) => setRow(items, setItems, i, { action: e.target.value })} {...invalid(`items.${i}.action`)} />
              {error(`items.${i}.action`)}
            </div>
            <div className="field">
              <label htmlFor={fid(`items.${i}.due_at`)}>Due (IST)</label>
              <input id={fid(`items.${i}.due_at`)} type="datetime-local" min={now} value={item.due} onChange={(e) => setRow(items, setItems, i, { due: e.target.value })} {...invalid(`items.${i}.due_at`)} />
              {error(`items.${i}.due_at`)}
            </div>
            <div className="field">
              <label htmlFor={fid(`items.${i}.reason`)}>Follow-up reason</label>
              <select id={fid(`items.${i}.reason`)} value={item.reason} onChange={(e) => setRow(items, setItems, i, { reason: e.target.value })} {...invalid(`items.${i}.reason`)}>
                <option value="">Select a reason</option>
                {REASONS.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
              </select>
              {error(`items.${i}.reason`)}
            </div>
            <button type="button" className="btn secondary small" onClick={() => setItems(items.filter((_, j) => j !== i))}>
              Remove<span className="visually-hidden"> action item {i + 1}</span>
            </button>
          </div>
        ))}
        {items.length < ROWS_MAX && (
          <div><button type="button" className="btn secondary small" onClick={() => setItems([...items, { action: "", due: "", reason: "" }])}>Add action item</button></div>
        )}
        {items.length > 0 && <p className="muted" style={{ margin: 0, fontSize: 13 }}>Each action item is added to the company&apos;s follow-ups.</p>}
      </fieldset>
      {meeting.commercial_notes_visible && (
        <div className="field">
          <label htmlFor={fid("commercial_notes")}>Commercial discussion notes</label>
          <textarea id={fid("commercial_notes")} rows={2} maxLength={COMMERCIAL_NOTES_MAX} value={v.commercial_notes}
            onChange={(e) => setV({ ...v, commercial_notes: e.target.value })} {...invalid("commercial_notes")} />
          {error("commercial_notes")}
        </div>
      )}
      {failure && (
        <div role="alert">
          <p className="form-error">{failure.message}</p>
          {failure.kind === "session" && <ReturnToLoginLink loginHref={RECRUITER_SIGN_IN} />}
        </div>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save outcome"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function historyText(h: HistoryEvent): string {
  const by = ` by ${h.actor.full_name}`;
  if (h.event === "rescheduled") {
    const from = h.old_starts_at ? formatSchoolDateTime(h.old_starts_at, true) : "?";
    const to = h.new_starts_at ? formatSchoolDateTime(h.new_starts_at, true) : "?";
    return `Rescheduled from ${from} to ${to}${by}${h.reason ? ` — ${h.reason}` : ""}`;
  }
  return `${h.event[0].toUpperCase()}${h.event.slice(1)} ${formatSchoolDateTime(h.created_at)}${by}`;
}

/** rec-028 (spec §4): one meeting with its actions -- Record outcome (once started), Edit/reschedule and Cancel (with a reason) -- offered
 *  only when the API allows them. `card` is the list form (the company first, linked); without it the item sits on its company's page.
 *  A refusal (changed elsewhere: 403/404/409) is handed up so the list reloads. */
export default function RecruiterMeetingItem({ meeting: m, card = false, contacts = [], onChanged, onRefused }: {
  meeting: RecMeeting; card?: boolean; contacts?: ContactOption[]; onChanged: (m: RecMeeting, notice: string) => void; onRefused: (message: string) => void;
}) {
  const [mode, setMode] = useState<"view" | "edit" | "outcome" | "cancel">("view");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const id = useId();
  const link = safeLink(m.meeting_url);

  async function cancel(reason: string) {
    setBusy(true);
    setFailure(null);
    const result = await sendJson(meetingUrl(m.id, "cancel"), "POST", { reason });
    setBusy(false);
    if (result.ok) return isRecMeeting(result.data) ? onChanged(result.data, "Meeting cancelled.") : setFailure({ kind: "error", message: SAVE_FAILED });
    const f = failureOf(result);
    return f.kind === "changed" ? onRefused(f.message) : setFailure(f);
  }

  const people = [...m.participants.contacts.map((c) => c.name), ...m.participants.recruiters.map((r) => r.full_name)];
  const facts = [
    card && ["Type", meetingTypeLabel(m.meeting_type)],
    ["When", formatSchoolDateTime(m.starts_at, true)],
    ["Mode", m.mode],
    m.location && ["Location", m.location],
    m.contact && ["Contact", m.contact.name],
    people.length > 0 && ["Participants", people.join(", ")],
    card && ["Recruiter", m.company.assigned_recruiter?.full_name ?? "Unassigned"],
  ].filter(Boolean) as [string, string][];
  const reschedules = m.history.filter((h) => h.event === "rescheduled");
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-title`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        {card ? (
          <strong id={`${id}-title`}>
            <Link href={`${COMPANIES_PATH}/${encodeURIComponent(m.company.id)}`} style={LINK_STYLE}>{m.company.name}</Link>{" "}
            <span className="muted" style={{ fontWeight: 400 }}>{m.company.code}</span>
          </strong>
        ) : (
          <strong id={`${id}-title`}>{meetingTypeLabel(m.meeting_type)}</strong>
        )}
        <span className="muted" style={{ fontSize: 13 }}>{m.code}</span>
        {m.status === "scheduled" && m.can_record_outcome && <span className="badge status pending">Awaiting outcome</span>}
        {m.status === "completed" && <span className="badge">Completed</span>}
        {m.status === "cancelled" && <span className="badge">Cancelled</span>}
      </div>
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))", gap: "4px 16px", margin: 0 }}>
        {facts.map(([term, value]) => (
          <div key={term}>
            <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
            <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
          </div>
        ))}
      </dl>
      {link && (
        <p style={{ margin: 0, overflowWrap: "anywhere" }}>
          <a href={link} target="_blank" rel="noopener noreferrer">Meeting link<span className="visually-hidden"> (opens in a new tab)</span></a>
        </p>
      )}
      {m.purpose && <p style={{ ...TEXT, margin: 0 }}>{m.purpose}</p>}
      {m.status === "completed" && (
        <div>
          <p style={{ ...TEXT, margin: 0 }}><strong>Outcome:</strong> {m.outcome}</p>
          {m.next_action && (
            <p className="muted" style={{ ...TEXT, margin: 0 }}>
              Next action: {m.next_action}{m.follow_up && ` (follow-up due ${formatSchoolDateTime(m.follow_up.due_at, true)})`}
            </p>
          )}
          {!!m.hiring_forecast?.length && (
            <p style={{ ...TEXT, margin: 0 }}>
              <strong>Hiring forecast:</strong> {m.hiring_forecast.map((r) => `${r.role} × ${r.count} (${timeframeLabel(r.timeframe)})`).join("; ")}
            </p>
          )}
          {m.commercial_notes && <p style={{ ...TEXT, margin: 0 }}><strong>Commercial discussion:</strong> {m.commercial_notes}</p>}
          {!!m.action_items?.length && (
            <div>
              <strong style={{ fontSize: 14 }}>Action items</strong>
              <ul style={{ margin: "2px 0 0", paddingLeft: 18 }}>
                {m.action_items.map((a) => (
                  <li key={a.follow_up_id} style={TEXT}>
                    {a.action} <span className="muted">— {reasonLabel(a.reason)}, due {formatSchoolDateTime(a.due_at, true)}{a.status !== "open" ? ` (${a.status})` : ""}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {m.cancelled_at && <p className="muted" style={{ ...TEXT, margin: 0 }}>Cancelled {formatSchoolDateTime(m.cancelled_at)}{m.cancel_reason && ` — ${m.cancel_reason}`}</p>}
      {reschedules.length > 0 && (
        <details>
          <summary style={{ cursor: "pointer", fontSize: 13 }}>History ({m.history.length})</summary>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 13 }}>
            {m.history.map((h, i) => <li key={`${h.created_at}-${i}`} style={TEXT}>{historyText(h)}</li>)}
          </ul>
        </details>
      )}
      {mode === "edit" && (
        <RecruiterMeetingForm companyId={m.company.id} contacts={contacts} meeting={m} onCancel={() => setMode("view")}
          onSaved={(next) => { setMode("view"); onChanged(next, "Meeting updated."); }} />
      )}
      {mode === "outcome" && (
        <OutcomeForm meeting={m} onCancel={() => setMode("view")} onRefused={onRefused}
          onSaved={(next) => { setMode("view"); onChanged(next, next.action_items?.length ? "Outcome saved and follow-ups added." : next.follow_up ? "Outcome saved and follow-up added." : "Outcome saved."); }} />
      )}
      {mode === "cancel" && (
        <BdmAppointmentReasonForm label="Cancel meeting" submitText="Cancel it" busyText="Cancelling…" busy={busy}
          onSubmit={(reason) => void cancel(reason)} onCancel={() => setMode("view")} />
      )}
      {mode === "view" && m.can_change && (
        <div className="actions">
          {m.can_record_outcome && <button type="button" className="btn small" onClick={() => setMode("outcome")}>Record outcome</button>}
          <button type="button" className="btn secondary small" onClick={() => setMode("edit")}>Reschedule / edit</button>
          <button type="button" className="btn secondary small" onClick={() => setMode("cancel")}>Cancel meeting</button>
        </div>
      )}
      {failure && (
        <div role="alert">
          <p className="form-error">{failure.message}</p>
          {failure.kind === "session" && <ReturnToLoginLink loginHref={RECRUITER_SIGN_IN} />}
        </div>
      )}
    </li>
  );
}

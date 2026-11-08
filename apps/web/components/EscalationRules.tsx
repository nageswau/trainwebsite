"use client";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import { SAVE_FAILED, writeFailure } from "@/lib/bdmTasks";
import {
  ESCALATION_RULES_URL,
  type EscalationRule,
  EVENT_TYPES,
  eventLabel,
  type EventType,
  HOURS_MAX,
  NOTIFY,
  type Notify,
  notifyLabel,
  validHours,
} from "@/lib/recruiterAutomation";

/** pob-027 (DEC-SCOPE-434 I7/I10): the Team Lead's escalation rules. A rule is added, or switched off and on; it is never deleted, so what
 * already fired keeps its record. Every item escalates once per rule. */
export default function EscalationRules() {
  const id = useId();
  const [rules, setRules] = useState<EscalationRule[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [eventType, setEventType] = useState<EventType>("requirement_unowned");
  const [hours, setHours] = useState("24");
  const [notify, setNotify] = useState<Notify>("reporting_manager");
  const [hoursError, setHoursError] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch(ESCALATION_RULES_URL, { signal: controller.signal })
      .then(async (r) => (r.ok ? setRules((await r.json()).items) : setLoadFailed(true)))
      .catch(() => !controller.signal.aborted && setLoadFailed(true));
    return () => controller.abort();
  }, []);

  async function run(send: () => ReturnType<typeof sendJson>, done: (data: { rule: EscalationRule }) => void, success: string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setMessage(null);
    const result = await send();
    inFlight.current = false;
    setBusy(false);
    if (!result.ok) return setMessage({ ok: false, text: writeFailure(result.status) === "retry" ? SAVE_FAILED : result.message });
    done(result.data as { rule: EscalationRule });
    setMessage({ ok: true, text: success });
  }

  async function add(event: FormEvent) {
    event.preventDefault();
    if (!validHours(hours)) return setHoursError(`Enter whole hours from 1 to ${HOURS_MAX}`);
    setHoursError(null);
    await run(() => sendJson(ESCALATION_RULES_URL, "POST", { event_type: eventType, after_hours: Number(hours), notify }),
      ({ rule }) => setRules((current) => [...(current ?? []), rule]), "Escalation rule added.");
  }

  const toggle = (rule: EscalationRule) =>
    run(() => sendJson(`${ESCALATION_RULES_URL}/${rule.id}`, "PATCH", { active: !rule.active }),
      ({ rule: saved }) => setRules((current) => (current ?? []).map((r) => (r.id === saved.id ? saved : r))),
      rule.active ? "Escalation rule switched off." : "Escalation rule switched on.");

  const hint = EVENT_TYPES.find((e) => e.value === eventType)?.hint;
  return (
    <section className="action-card" aria-labelledby={`${id}-title`} style={{ marginBottom: 16 }}>
      <h3 id={`${id}-title`} style={{ marginTop: 0 }}>Escalation rules</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        When an item is still waiting after the given hours, the Team Lead gets a notice. Each item is escalated once per rule; a new rule covers
        items from the time it is added.
      </p>
      {loadFailed && <p className="form-error" role="alert">The escalation rules could not be loaded. Refresh the page to try again.</p>}
      {!rules && !loadFailed && <p className="muted" role="status">Loading escalation rules…</p>}
      {rules && rules.length === 0 && <p className="muted">No escalation rules yet.</p>}
      {rules && rules.length > 0 && (
        <table className="table compact stack">
          <thead>
            <tr><th scope="col">When</th><th scope="col">After</th><th scope="col">Tell</th><th scope="col">Added</th><th scope="col">Status</th><th scope="col"><span className="visually-hidden">Action</span></th></tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.id}>
                <td data-label="When">{eventLabel(rule.event_type)}</td>
                <td data-label="After">{rule.after_hours} h</td>
                <td data-label="Tell">{notifyLabel(rule.notify)}</td>
                <td data-label="Added"><LocalTime value={rule.created_at} /></td>
                <td data-label="Status">{rule.active ? "On" : "Off"}</td>
                <td>
                  <button type="button" className="btn small secondary" disabled={busy} onClick={() => toggle(rule)}>{rule.active ? "Switch off" : "Switch on"}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {rules && (
        <form noValidate onSubmit={add} aria-label="Add an escalation rule" style={{ marginTop: 12 }}>
          <div className="form-grid" style={{ display: "grid", gap: 8, alignItems: "start", gridTemplateColumns: "repeat(auto-fit, minmax(min(13rem, 100%), 1fr))" }}>
            <div className="field">
              <label htmlFor={`${id}-event`}>When</label>
              <select id={`${id}-event`} value={eventType} onChange={(e) => setEventType(e.target.value as EventType)}>
                {EVENT_TYPES.map((e) => <option key={e.value} value={e.value}>{e.label}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor={`${id}-hours`}>After (hours)</label>
              <input id={`${id}-hours`} type="number" inputMode="numeric" min={1} max={HOURS_MAX} step={1} value={hours} onChange={(e) => setHours(e.target.value)}
                aria-invalid={hoursError ? true : undefined} aria-describedby={`${id}-hours-hint${hoursError ? ` ${id}-hours-error` : ""}`} />
              <p id={`${id}-hours-hint`} className="muted" style={{ margin: 0, fontSize: 13 }}>{hint}</p>
              {hoursError && <p id={`${id}-hours-error`} className="form-error">{hoursError}</p>}
            </div>
            <div className="field">
              <label htmlFor={`${id}-notify`}>Tell</label>
              <select id={`${id}-notify`} value={notify} onChange={(e) => setNotify(e.target.value as Notify)}>
                {NOTIFY.map((n) => <option key={n.value} value={n.value}>{n.label}</option>)}
              </select>
            </div>
          </div>
          {message && <p className={message.ok ? "muted" : "form-error"} role={message.ok ? "status" : "alert"}>{message.text}</p>}
          <div className="actions" style={{ marginTop: 12 }}>
            <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Add rule"}</button>
          </div>
        </form>
      )}
    </section>
  );
}

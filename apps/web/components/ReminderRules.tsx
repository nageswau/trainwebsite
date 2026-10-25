"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmTravel";
import LocalTime from "@/components/LocalTime";
import {
  actionLabel, offsetError, offsetUnit, REMINDER_RULES_API, runSummary, type ReminderLogPage, type ReminderRule, type ReminderRunCounts,
} from "@/lib/reminderRules";
import { useHydrated } from "@/lib/useHydrated";

type Message = { text: string; failed: boolean } | null;

function Status({ message }: { message: Message }) {
  return message ? <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>{message.text}</p> : null;
}

// ccrm-030 (RM9): one rule -- on/off, its offset and (where the rule has one) the student reminder -- saved on its own.
function RuleCard({ rule }: { rule: ReminderRule }) {
  const router = useRouter();
  const ready = useHydrated();
  const [enabled, setEnabled] = useState(rule.enabled);
  const [offset, setOffset] = useState(String(rule.offset_days));
  const [student, setStudent] = useState(Boolean(rule.notify_student));
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<Message>(null);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false); // one save per double click
  const id = `rule-${rule.key}`;

  async function save() {
    if (sending.current) return;
    const found = offsetError(rule, offset);
    setError(found);
    if (found) {
      setMessage(null);
      document.getElementById(`${id}-offset`)?.focus();
      return;
    }
    sending.current = true;
    setBusy(true);
    setMessage(null);
    const payload: Record<string, unknown> = { enabled, offset_days: Number(offset) };
    if (rule.notify_student !== null) payload.notify_student = student;
    const saved = await sendJson(`${REMINDER_RULES_API}/${rule.key}`, "PUT", payload);
    sending.current = false;
    setBusy(false);
    if (!saved.ok) {
      const placed = fieldErrors(saved.detail);
      setError(placed.offset_days ?? null);
      setMessage({ text: placed.offset_days ? "Check the highlighted field." : saved.message, failed: true });
      return;
    }
    setMessage({ text: "Saved.", failed: false });
    router.refresh();
  }

  return (
    <form className="panel" noValidate aria-labelledby={`${id}-title`} onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <fieldset disabled={!ready || busy} className="form" style={{ border: 0, padding: 0, margin: 0, minWidth: 0, gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "baseline" }}>
          <h3 id={`${id}-title`} style={{ margin: 0 }}>{rule.label}</h3>
          <span className="badge">{actionLabel(rule)}</span>
        </div>
        <p className="muted" style={{ margin: 0 }}>{rule.description}</p>
        {/* QA-03: the switches sit under the offset, not beside its hint */}
        <div className="field" style={{ margin: 0, maxWidth: 320 }}>
          <label htmlFor={`${id}-offset`}>{offsetUnit(rule.timing).replace(/^days/, "Days")}</label>
          <input
            id={`${id}-offset`} type="number" inputMode="numeric" min={rule.min_offset} max={rule.max_offset} step={1} value={offset}
            onChange={(e) => { setOffset(e.target.value); setError(null); setMessage(null); }}
            aria-invalid={error ? true : undefined} aria-describedby={error ? `${id}-offset-error` : `${id}-offset-hint`}
          />
          {error ? <p className="form-error" id={`${id}-offset-error`}>{error}</p> : <span className="muted" id={`${id}-offset-hint`} style={{ fontSize: 12 }}>{rule.min_offset}–{rule.max_offset}</span>}
        </div>
        <div style={{ display: "grid", gap: 8 }}>
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={enabled} onChange={(e) => { setEnabled(e.target.checked); setMessage(null); }} /> Rule is on
          </label>
          {rule.notify_student !== null && (
            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={student} onChange={(e) => { setStudent(e.target.checked); setMessage(null); }} /> Also remind the student (direct students only)
            </label>
          )}
        </div>
        <div className="actions">
          <button className="btn" type="submit">{busy ? "Saving…" : "Save"}</button>
        </div>
        <Status message={message} />
      </fieldset>
    </form>
  );
}

// RM10: run the daily job now -- the same de-duplication, so a second click sends nothing new.
function RunNow() {
  const router = useRouter();
  const ready = useHydrated();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Message>(null);

  async function run() {
    if (busy) return;
    setBusy(true);
    setMessage(null);
    const done = await sendJson(`${REMINDER_RULES_API}/run`, "POST", {});
    setBusy(false);
    if (!done.ok) return setMessage({ text: done.message, failed: true });
    setMessage({ text: runSummary(done.data as ReminderRunCounts), failed: false });
    router.refresh();
  }

  return (
    <div className="panel" style={{ display: "grid", gap: 12 }}>
      <div>
        <h3 style={{ margin: 0 }}>Run reminders now</h3>
        <p className="muted" style={{ margin: "6px 0 0" }}>The job runs every day at 08:15 IST. Running it now never sends a reminder twice — use it to test the rules with sample records.</p>
      </div>
      <div className="actions">
        <button className="btn" type="button" onClick={() => void run()} disabled={!ready || busy} aria-busy={busy}>{busy ? "Running…" : "Run reminders now"}</button>
      </div>
      <Status message={message} />
    </div>
  );
}

export default function ReminderRules({ rules, log }: { rules: ReminderRule[]; log: ReminderLogPage }) {
  return (
    <div style={{ display: "grid", gap: 24, maxWidth: 900 }}>
      <RunNow />
      <section aria-labelledby="rules-heading" style={{ display: "grid", gap: 14 }}>
        <h3 id="rules-heading" style={{ margin: 0 }}>Rules</h3>
        {rules.map((rule) => <RuleCard key={rule.key} rule={rule} />)}
      </section>
      <section aria-labelledby="log-heading" className="workspace">
        <div className="workspace-head"><h3 id="log-heading" style={{ margin: 0 }}>Recent reminders</h3><span className="muted">{log.total} in total</span></div>
        {log.items.length === 0 ? (
          <p className="empty">No reminder has been sent yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th scope="col">When</th><th scope="col">Rule</th><th scope="col">About</th><th scope="col">Task</th><th scope="col">Told</th></tr></thead>
              <tbody>
                {log.items.map((item) => (
                  <tr key={item.id}>
                    <td className="no-wrap"><LocalTime value={item.created_at} time /></td>
                    <td>{item.rule_label}</td>
                    <td>{item.summary}</td>
                    <td>{item.task_created ? "Task added" : "—"}</td>
                    <td>{item.recipients}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

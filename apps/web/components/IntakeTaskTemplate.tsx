"use client";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { SAVE_FAILED, writeFailure } from "@/lib/bdmTasks";
import { HOURS_MAX, INTAKE_SETTINGS_URL, type IntakeSettings, TASK_KINDS, type TaskKind, TEMPLATE_MAX, validHours } from "@/lib/recruiterAutomation";

type Row = { kind: TaskKind; title: string; hours: string };
const toRows = (s: IntakeSettings): Row[] => s.task_template.map((t) => ({ kind: t.kind, title: t.title, hours: String(t.due_in_hours) }));

/** pob-027 (DEC-SCOPE-434 I3/I10): the tasks a requirement's first owner starts with. One form, saved as a whole; the API checks every rule
 * and its 422s are shown as one message. */
export default function IntakeTaskTemplate() {
  const id = useId();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch(INTAKE_SETTINGS_URL, { signal: controller.signal })
      .then(async (r) => (r.ok ? setRows(toRows(await r.json())) : setLoadFailed(true)))
      .catch(() => !controller.signal.aborted && setLoadFailed(true));
    return () => controller.abort();
  }, []);

  const change = (index: number, patch: Partial<Row>) => rows && setRows(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!rows || inFlight.current) return;
    const found: Record<string, string> = {};
    rows.forEach((row, i) => {
      if (!row.title.trim()) found[`${i}-title`] = "Enter a title";
      if (!validHours(row.hours)) found[`${i}-hours`] = `Enter whole hours from 1 to ${HOURS_MAX}`;
    });
    setErrors(found);
    setMessage(null);
    if (Object.keys(found).length) return;
    inFlight.current = true;
    setBusy(true);
    const result = await sendJson(INTAKE_SETTINGS_URL, "PUT", { task_template: rows.map((r) => ({ kind: r.kind, title: r.title.trim(), due_in_hours: Number(r.hours) })) });
    inFlight.current = false;
    setBusy(false);
    if (result.ok) {
      setRows(toRows(result.data as IntakeSettings));
      return setMessage({ ok: true, text: "Task template saved." });
    }
    setMessage({ ok: false, text: writeFailure(result.status) === "retry" ? SAVE_FAILED : result.message });
  }

  return (
    <section className="action-card" aria-labelledby={`${id}-title`} style={{ marginBottom: 16 }}>
      <h3 id={`${id}-title`} style={{ marginTop: 0 }}>New requirement tasks</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        When a requirement gets its first owner, these tasks are created for them once, due the given hours later. A reassignment moves the open
        ones to the new owner.
      </p>
      {loadFailed && <p className="form-error" role="alert">The task template could not be loaded. Refresh the page to try again.</p>}
      {!rows && !loadFailed && <p className="muted" role="status">Loading the task template…</p>}
      {rows && (
        <form noValidate onSubmit={submit} aria-label="New requirement tasks">
          {rows.length === 0 && <p className="muted">No tasks: a new owner starts with none.</p>}
          {rows.map((row, i) => {
            const n = i + 1;
            const base = `${id}-${i}`;
            return (
              <fieldset key={i} className="form-grid" style={{ border: 0, padding: 0, margin: "0 0 8px", display: "grid", gap: 8, alignItems: "end",
                gridTemplateColumns: "repeat(auto-fit, minmax(min(11rem, 100%), 1fr))" }}>
                <legend className="sr-only">Task {n}</legend>
                <div className="field">
                  <label htmlFor={`${base}-kind`}>Task {n} type</label>
                  <select id={`${base}-kind`} value={row.kind} onChange={(e) => change(i, { kind: e.target.value as TaskKind })}>
                    {TASK_KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor={`${base}-title`}>Task {n} title</label>
                  <input id={`${base}-title`} maxLength={200} value={row.title} onChange={(e) => change(i, { title: e.target.value })}
                    aria-invalid={errors[`${i}-title`] ? true : undefined} aria-describedby={errors[`${i}-title`] ? `${base}-title-error` : undefined} />
                  {errors[`${i}-title`] && <p id={`${base}-title-error`} className="form-error">{errors[`${i}-title`]}</p>}
                </div>
                <div className="field">
                  <label htmlFor={`${base}-hours`}>Task {n} due after (hours)</label>
                  <input id={`${base}-hours`} type="number" inputMode="numeric" min={1} max={HOURS_MAX} step={1} value={row.hours}
                    onChange={(e) => change(i, { hours: e.target.value })}
                    aria-invalid={errors[`${i}-hours`] ? true : undefined} aria-describedby={errors[`${i}-hours`] ? `${base}-hours-error` : undefined} />
                  {errors[`${i}-hours`] && <p id={`${base}-hours-error`} className="form-error">{errors[`${i}-hours`]}</p>}
                </div>
                <div>
                  <button type="button" className="btn small secondary" aria-label={`Remove task ${n}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                    Remove
                  </button>
                </div>
              </fieldset>
            );
          })}
          {message && <p className={message.ok ? "muted" : "form-error"} role={message.ok ? "status" : "alert"}>{message.text}</p>}
          <div className="actions" style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" className="btn small secondary" disabled={rows.length >= TEMPLATE_MAX}
              onClick={() => setRows([...rows, { kind: "sourcing", title: "", hours: "24" }])}>Add task</button>
            <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save tasks"}</button>
          </div>
          {rows.length >= TEMPLATE_MAX && <p className="muted" style={{ fontSize: 13 }}>At most {TEMPLATE_MAX} tasks.</p>}
        </form>
      )}
    </section>
  );
}

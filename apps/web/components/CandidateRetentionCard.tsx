"use client";

import { type FormEvent, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import { type Retention, RETENTION_URL } from "@/lib/candidateDataRequests";

// hrc-035 (DEC-SCOPE-396 K8): the retention rule. Off by default (no period has legal sign-off yet); super_admin turns it on or off.
export default function CandidateRetentionCard({ initial }: { initial: Retention }) {
  const [state, setState] = useState(initial);
  const [months, setMonths] = useState(initial.months?.toString() ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [min, max] = state.range;

  async function save(value: number | null) {
    if (busy) return;
    setBusy(true);
    setMessage(null);
    const outcome = await sendJson(RETENTION_URL, "PUT", { months: value });
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: !outcome.status || outcome.status >= 500 ? "The rule was not saved. Please try again." : outcome.message, failed: true });
    const next = outcome.data as Retention;
    setState(next);
    setMonths(next.months?.toString() ?? "");
    setMessage({ text: next.months ? `Saved. Inactive candidates are anonymised after ${next.months} months.` : "The retention rule is off.", failed: false });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = Number(months);
    if (!Number.isInteger(value) || value < min || value > max) return setMessage({ text: `Enter a whole number of months from ${min} to ${max}.`, failed: true });
    void save(value);
  }

  return (
    <section className="card" aria-labelledby="retention-title">
      <h3 id="retention-title">Retention rule</h3>
      <p>
        Status: <span className={state.months ? "status" : "status pending"}>{state.months ? `On — ${state.months} months after the last activity` : "Off"}</span>
      </p>
      <p className="muted">
        When on, a daily job anonymises candidates with no activity for the chosen time, unless they have an open application, an offer in
        progress or are students. {state.months ? `${state.due_now} candidate${state.due_now === 1 ? " is" : "s are"} due now.` : ""}
        {state.last_run_at && <> Last run <LocalTime value={state.last_run_at} time />: {state.last_run_count ?? 0} anonymised.</>}
      </p>
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>{message.text}</p>}
      {state.can_edit ? (
        <form onSubmit={submit} noValidate style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div className="field">
            <label htmlFor="retention-months">Months after the last activity</label>
            <input id="retention-months" type="number" inputMode="numeric" min={min} max={max} step={1} value={months} disabled={busy} onChange={(e) => setMonths(e.target.value)} />
          </div>
          <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Save rule"}</button>
          {state.months !== null && <button className="btn secondary" type="button" disabled={busy} onClick={() => void save(null)}>Turn off</button>}
        </form>
      ) : <p className="muted" style={{ margin: 0 }}>Only a super admin can change this rule.</p>}
    </section>
  );
}

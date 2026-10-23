"use client";

import { FormEvent, useRef, useState } from "react";
import { sendJson } from "@/lib/apiErrors";
import { todayIso } from "@/lib/agentApplications";
import { outcomeChoices, outcomeLabel, REQUESTERS, type SettableOutcome } from "@/lib/applicationOutcome";

type Props = {
  id: string;
  stage: string;
  outcome: string | null | undefined;
  onSaved: (data: Record<string, unknown>, message: string) => void;
  onFailed: (message: string, status?: number) => void;
  onCancel: () => void;
};


// ccrm-015 (DEC-SCOPE-244): record an exception outcome on ONE application. Each outcome asks only for its own fields; the server is
// the authority on every rule (required fields, closed / enrolled, the offer stage, a past review date).
export default function ApplicationOutcomeForm({ id, stage, outcome, onSaved, onFailed, onCancel }: Props) {
  const choices = outcomeChoices(stage, outcome);
  const [kind, setKind] = useState<SettableOutcome>(choices[0] ?? "rejected");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a same-tick second submit sends nothing
  const today = todayIso();
  const field = (name: string) => `outcome-${name}-${id}`;
  const reasonOptional = kind === "deferred";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const form = new FormData(event.currentTarget);
    const text = (name: string) => String(form.get(name) ?? "").trim() || null;
    const body: Record<string, unknown> = { outcome: kind, reason: text("reason"), outcome_date: text("outcome_date") };
    if (kind === "rejected") body.next_steps = text("next_steps");
    if (kind === "withdrawn") body.requested_by = text("requested_by");
    if (kind === "deferred") Object.assign(body, { new_intake: text("new_intake"), application_deadline: text("application_deadline"), offer_deadline: text("offer_deadline") });
    if (kind === "on_hold") body.review_date = text("review_date");
    if (kind === "offer_declined") body.another_offer_preferred = form.get("another_offer_preferred") === "on";
    inFlight.current = true;
    setBusy(true);
    let result: Awaited<ReturnType<typeof sendJson>>;
    try {
      result = await sendJson(`/api/v1/workflows/overseas/applications/${id}/outcome`, "POST", body);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
    if (!result.ok) return onFailed(result.message, result.status);
    onSaved(result.data, `Outcome recorded: ${outcomeLabel(kind)}.`);
  }

  if (!choices.length) return null;
  return (
    <form className="form" onSubmit={submit} aria-label="Record outcome" onKeyDown={(event) => event.key === "Escape" && !busy && onCancel()}>
      <div className="field">
        <label htmlFor={field("kind")}>Outcome</label>
        <select id={field("kind")} value={kind} onChange={(event) => setKind(event.target.value as SettableOutcome)} autoFocus>
          {choices.map((o) => (
            <option key={o} value={o}>
              {outcomeLabel(o)}
            </option>
          ))}
        </select>
      </div>
      {kind === "withdrawn" && (
        <div className="field">
          <label htmlFor={field("requested_by")}>Requested by</label>
          <select id={field("requested_by")} name="requested_by" required defaultValue="student">
            {REQUESTERS.map((r) => (
              <option key={r} value={r}>
                {outcomeLabel(r)}
              </option>
            ))}
          </select>
        </div>
      )}
      {kind === "deferred" && (
        <>
          <div className="field">
            <label htmlFor={field("new_intake")}>New intake</label>
            <input id={field("new_intake")} name="new_intake" required maxLength={80} placeholder="e.g. January 2028" />
          </div>
          <div className="field">
            <label htmlFor={field("application_deadline")}>Revised application deadline (optional)</label>
            <input id={field("application_deadline")} name="application_deadline" type="date" />
          </div>
          <div className="field">
            <label htmlFor={field("offer_deadline")}>Revised offer deadline (optional)</label>
            <input id={field("offer_deadline")} name="offer_deadline" type="date" />
          </div>
        </>
      )}
      {kind === "on_hold" && (
        <div className="field">
          <label htmlFor={field("review_date")}>Review date</label>
          <input id={field("review_date")} name="review_date" type="date" required min={today} />
        </div>
      )}
      <div className="field">
        <label htmlFor={field("reason")}>{reasonOptional ? "Reason (optional)" : "Reason"}</label>
        <textarea id={field("reason")} name="reason" maxLength={2000} required={!reasonOptional} />
      </div>
      {kind === "rejected" && (
        <div className="field">
          <label htmlFor={field("next_steps")}>Suggested next steps (optional)</label>
          <textarea id={field("next_steps")} name="next_steps" maxLength={2000} />
        </div>
      )}
      {kind === "offer_declined" && (
        <div className="field">
          <label>
            <input type="checkbox" name="another_offer_preferred" /> The student prefers another offer
          </label>
        </div>
      )}
      <div className="field">
        <label htmlFor={field("outcome_date")}>Date (optional, default today)</label>
        <input id={field("outcome_date")} name="outcome_date" type="date" max={today} />
      </div>
      <div className="actions">
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : "Record outcome"}
        </button>
        <button type="button" className="btn ghost small" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

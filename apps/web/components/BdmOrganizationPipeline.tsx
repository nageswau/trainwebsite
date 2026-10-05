"use client";
import { type FormEvent, useRef, useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { isOrganizationBody, type Organization, ORGS_URL } from "@/lib/bdmOrganizations";
import { fieldErrors, isBackward, lostConflict, orgActionUrl, stageChanged, STATE_TEXT, type StepState } from "@/lib/bdmPipeline";
import { formatDate } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const GLYPH: Record<StepState, string> = { done: "✓", current: "•", upcoming: "–", awaiting_handover: "…", not_tracked: "–" };

const REFRESH_FAILED = "Unable to show the latest stage. Reload the page.";

// bdm-004 (spec §8.2): the stepper (state as text, never colour alone), the derived agent status, the Lost banner, and -- for the
// assigned BDM or super_admin (permissions.can_edit) -- Move, Mark lost and Revive. The API enforces every rule; a refusal keeps the
// entry. Each success hands the returned organization to the detail page (`onChanged`, with the notice); when someone else changed it
// meanwhile, the fresh organization goes to `onRefreshed` and the reason is shown here as an error, keeping what was typed (QA4-07).
export default function BdmOrganizationPipeline({ organization: org, onChanged, onRefreshed }: {
  organization: Organization; onChanged: (o: Organization, text: string) => void; onRefreshed?: (o: Organization) => void;
}) {
  const p = org.pipeline;
  const canWrite = org.permissions.can_edit;
  const [to, setTo] = useState("");
  const [note, setNote] = useState("");
  const [mode, setMode] = useState<"lost" | "revive" | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const inFlight = useRef(false); // QA4-06: a second submit before the re-render (double click) sends nothing
  const focus = useFocusAfterRender();
  const id = (part: string) => `pipeline-${org.id}-${part}`;
  const backward = to !== "" && isBackward(p, to);
  const labelOf = (key: string) => p.steps.find((s) => s.key === key)?.label ?? key;

  const resetForms = () => {
    setTo("");
    setNote("");
    setReason("");
    setMode(null);
  };
  async function latest(): Promise<Organization | null> {
    const fresh = await sendRequest(`${ORGS_URL}/${org.id}`, { method: "GET" });
    return fresh.ok && isOrganizationBody(fresh.data) ? fresh.data.organization : null;
  }

  async function send(action: "stage" | "lost" | "revive", body: Record<string, string>, success: string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    setErrors({});
    try {
      const outcome = await sendJson(orgActionUrl(org.id, action), "POST", body);
      if (outcome.ok && isOrganizationBody(outcome.data)) {
        resetForms();
        return onChanged(outcome.data.organization, success);
      }
      if (outcome.ok) return setFailure("Unable to update this organization.");
      const current = stageChanged(outcome.detail);
      if (current !== null && current === body.to_stage) { // Review Focus 1: a retried move that already landed is a success
        const fresh = await latest();
        resetForms();
        return fresh ? onChanged(fresh, success) : setFailure(REFRESH_FAILED);
      }
      const conflict = current !== null ? `${(outcome.detail as { message: string }).message}. Check the stage and try again.` : lostConflict(outcome.detail);
      if (conflict !== null) { // someone else changed it: show it as it is now and say why; the note / reason stay typed
        setTo("");
        setMode(null);
        const fresh = await latest();
        if (fresh) onRefreshed?.(fresh);
        return setFailure(fresh ? conflict : `${conflict} ${REFRESH_FAILED}`);
      }
      const fields = fieldErrors(outcome.detail);
      if (Object.keys(fields).length) setErrors(fields);
      else setFailure(outcome.message);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  function submitMove(event: FormEvent) {
    event.preventDefault();
    void send("stage", { from_stage: p.stage, to_stage: to, ...(note.trim() ? { note } : {}) }, `Moved to ${labelOf(to)}.`);
  }
  function submitFlag(event: FormEvent) {
    event.preventDefault();
    void send(mode === "lost" ? "lost" : "revive", { reason }, mode === "lost" ? "Marked lost." : "Revived.");
  }
  const openFlag = () => {
    setMode(p.lost ? "revive" : "lost");
    focus(id("reason"));
  };
  const cancelFlag = () => {
    setMode(null);
    setReason("");
    focus(id("flag"));
  };
  const fieldError = (field: string) =>
    errors[field] ? <p id={id(`${field}-error`)} className="form-error">{errors[field]}</p> : null;

  return (
    <section className="action-card wide" aria-label="Pipeline">
      <h3>Pipeline</h3>
      {p.agent_status && (
        <p>
          Agent status: <span className="badge">{p.agent_status}</span>
        </p>
      )}
      {p.lost && (
        <p className="form-message" style={{ whiteSpace: "pre-line" }}>
          Marked lost on {formatDate(p.lost.at)}: {p.lost.reason}
        </p>
      )}
      <ol className="jny-steps" aria-label="Pipeline stages">
        {p.steps.map((s) => (
          <li key={s.key} className={`jny-step jny-${s.state}`} aria-current={s.state === "current" ? "step" : undefined}>
            <span className="jny-glyph" aria-hidden="true">{GLYPH[s.state]}</span>
            <span className="jny-name">{s.label}</span>
            <span className="jny-state">{STATE_TEXT[s.state]}</span>
          </li>
        ))}
      </ol>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {canWrite && !p.lost && mode === null && (
        <form className="form-grid" onSubmit={submitMove} aria-label="Move stage">
          <div className="field">
            <label htmlFor={id("to")}>Move to</label>
            <select id={id("to")} value={to} onChange={(e) => setTo(e.target.value)} required aria-describedby={errors.to_stage ? id("to_stage-error") : undefined}>
              <option value="">Choose a stage</option>
              {p.steps.filter((s) => s.kind === "manual").map((s) => (
                <option key={s.key} value={s.key} disabled={s.key === p.stage}>
                  {s.label}{s.key === p.stage ? " (current)" : ""}
                </option>
              ))}
            </select>
            {fieldError("to_stage")}
          </div>
          <div className="field">
            <label htmlFor={id("note")}>{backward ? "Reason (required when moving back)" : "Note (optional)"}</label>
            <textarea id={id("note")} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} rows={2} required={backward} aria-describedby={errors.note ? id("note-error") : undefined} />
            {fieldError("note")}
          </div>
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy || to === ""}>
              {busy ? "Saving…" : "Move"}
            </button>
          </div>
        </form>
      )}
      {canWrite && mode === null && (
        <button id={id("flag")} type="button" className="btn secondary small" onClick={openFlag} disabled={busy}>
          {p.lost ? "Revive" : "Mark lost"}
        </button>
      )}
      {canWrite && mode !== null && (
        <form className="form-grid" onSubmit={submitFlag} aria-label={mode === "lost" ? "Mark lost" : "Revive"}>
          <div className="field">
            <label htmlFor={id("reason")}>Reason</label>
            <textarea id={id("reason")} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} rows={2} required aria-describedby={errors.reason ? id("reason-error") : undefined} />
            {fieldError("reason")}
          </div>
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy}>
              {busy ? "Saving…" : mode === "lost" ? "Yes, mark lost" : "Yes, revive"}
            </button>
            <button type="button" className="btn secondary small" onClick={cancelFlag} disabled={busy}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

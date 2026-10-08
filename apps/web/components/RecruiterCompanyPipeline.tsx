"use client";
import { type FormEvent, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { fieldErrors, stageChanged } from "@/lib/bdmPipeline";
import { type Company, COMPANIES_URL, isCompanyBody } from "@/lib/recruiterCompanies";
import { companyActionUrl, isBackward, lostConflict, STATE_TEXT, type PipelineStep } from "@/lib/recruiterPipeline";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const GLYPH: Record<PipelineStep["state"], string> = { done: "✓", current: "•", upcoming: "–" };
const REFRESH_FAILED = "Unable to show the latest stage. Reload the page.";
type Mode = "lost" | "reopen" | null;

// rec-005 (spec §5): the stepper (state as text, never colour alone), the Lost banner and -- from `pipeline.can_move` / `can_reopen` --
// Move (manual stages only), Mark lost and Reopen. The bdm-004 BdmOrganizationPipeline flow: the API enforces every rule, a refusal keeps
// what was typed, and when someone else changed the company meanwhile the fresh company goes to `onRefreshed` with the reason shown here.
export default function RecruiterCompanyPipeline({ company, onChanged, onRefreshed }: {
  company: Company; onChanged: (c: Company, text: string) => void; onRefreshed?: (c: Company) => void;
}) {
  const p = company.pipeline;
  const [to, setTo] = useState("");
  const [reason, setReason] = useState("");
  const [mode, setMode] = useState<Mode>(null);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const inFlight = useRef(false); // a second submit before the re-render (double click) sends nothing
  const focus = useFocusAfterRender();
  const id = (part: string) => `company-${company.id}-pipeline-${part}`;
  const atManual = p.steps.some((s) => s.key === p.stage && s.kind !== "driven");
  const backward = to !== "" && isBackward(p, to);
  const labelOf = (key: string) => p.steps.find((s) => s.key === key)?.label ?? key;

  const reset = () => {
    setTo("");
    setReason("");
    setMode(null);
  };
  async function latest(): Promise<Company | null> {
    const fresh = await sendRequest(`${COMPANIES_URL}/${company.id}`, { method: "GET" });
    return fresh.ok && isCompanyBody(fresh.data) ? fresh.data.company : null;
  }

  async function send(action: "stage" | "lost" | "reopen", body: Record<string, string>, success: string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    setErrors({});
    try {
      const outcome = await sendJson(companyActionUrl(company.id, action), "POST", body);
      if (outcome.ok && isCompanyBody(outcome.data)) {
        reset();
        return onChanged(outcome.data.company, success);
      }
      if (outcome.ok) return setFailure("Unable to update this company.");
      const current = stageChanged(outcome.detail);
      if (current !== null && current === body.to_stage) { // a retried move that already landed is a success
        const fresh = await latest();
        reset();
        return fresh ? onChanged(fresh, success) : setFailure(REFRESH_FAILED);
      }
      const conflict = current !== null ? `${(outcome.detail as { message: string }).message}. Check the stage and try again.` : lostConflict(outcome.detail);
      if (conflict !== null) { // someone else changed it: show it as it is now and say why; the reason stays typed
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
    void send("stage", { from_stage: p.stage, to_stage: to, ...(reason.trim() ? { reason } : {}) }, `Moved to ${labelOf(to)}.`);
  }
  function submitFlag(event: FormEvent) {
    event.preventDefault();
    void send(mode === "lost" ? "lost" : "reopen", { reason }, mode === "lost" ? "Marked lost." : "Reopened.");
  }
  const openFlag = (next: Mode) => {
    setMode(next);
    setReason("");
    focus(id("flag-reason"));
  };
  const cancelFlag = () => {
    setMode(null);
    setReason("");
    focus(id("flag"));
  };
  const fieldError = (field: string) => (errors[field] ? <p id={id(`${field}-error`)} className="form-error">{errors[field]}</p> : null);
  const flagButton = p.can_move ? "Mark lost" : p.can_reopen ? "Reopen" : null;

  return (
    <section className="action-card wide" aria-labelledby={id("heading")}>
      <h3 id={id("heading")}>Pipeline</h3>
      {p.lost && (
        <p className="form-message" style={{ whiteSpace: "pre-line", overflowWrap: "anywhere" }}>
          Marked lost on <LocalTime value={p.lost.at} />: {p.lost.reason}
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
      <p className="muted" style={{ margin: "0 0 10px", fontSize: 13 }}>
        At {p.stage_label} since <LocalTime value={p.stage_changed_at} time />.
        {!atManual && " The stage now moves with its job requirements."}
      </p>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {p.can_move && atManual && mode === null && (
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
            <label htmlFor={id("reason")}>{backward ? "Reason (required when moving back)" : "Note (optional)"}</label>
            <textarea id={id("reason")} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} rows={2} required={backward} aria-describedby={errors.reason ? id("reason-error") : undefined} />
            {fieldError("reason")}
          </div>
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy || to === ""}>
              {busy ? "Saving…" : "Move"}
            </button>
          </div>
        </form>
      )}
      {flagButton && mode === null && (
        <button id={id("flag")} type="button" className="btn secondary small" onClick={() => openFlag(p.can_move ? "lost" : "reopen")} disabled={busy}>
          {flagButton}
        </button>
      )}
      {mode !== null && (
        <form className="form-grid" onSubmit={submitFlag} aria-label={mode === "lost" ? "Mark lost" : "Reopen"}>
          <div className="field">
            <label htmlFor={id("flag-reason")}>Reason</label>
            <textarea id={id("flag-reason")} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} rows={2} required aria-describedby={errors.reason ? id("reason-error") : undefined} />
            {fieldError("reason")}
          </div>
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy}>
              {busy ? "Saving…" : mode === "lost" ? "Yes, mark lost" : "Yes, reopen"}
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

"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { fieldErrors, stageChanged } from "@/lib/bdmPipeline";
import { formatDate } from "@/lib/formatDate";
import { isBackward, lostConflict } from "@/lib/partnershipPipeline";
import { type University, universityUrl } from "@/lib/universities";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type State = "done" | "current" | "upcoming";
const GLYPH: Record<State, string> = { done: "✓", current: "•", upcoming: "–" };
const STATE_TEXT: Record<State, string> = { done: "Done", current: "Current", upcoming: "Upcoming" };

// upc-007 (spec §4, PS4-PS8): the 15 §3 stages (state as text, never colour alone), the Kanban column, the Lost banner, and -- per
// `permissions` -- Move (a note is required when moving back), Mark lost and Reopen, each with a reason. The API enforces every rule; a
// refusal keeps what was typed. A success, or a change someone else made meanwhile, refreshes the server-rendered page.
export default function UniversityStagePanel({ university: u }: { university: University }) {
  const router = useRouter();
  const p = u.pipeline;
  const { can_move_stage: canMove, can_reopen: canReopen } = u.permissions;
  const [to, setTo] = useState("");
  const [note, setNote] = useState("");
  const [mode, setMode] = useState<"lost" | "reopen" | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false); // a second submit before the re-render (double click) sends nothing
  const focus = useFocusAfterRender();
  const id = (part: string) => `stage-${u.id}-${part}`;
  const backward = to !== "" && isBackward(p, to);
  const current = p.stages.findIndex((s) => s.key === p.stage);
  const labelOf = (key: string) => p.stages.find((s) => s.key === key)?.label ?? key;
  const canFlag = p.lost ? canReopen : canMove;

  async function send(action: "stage" | "lost" | "reopen", body: Record<string, string>, success: string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    setErrors({});
    try {
      const outcome = await sendJson(universityUrl(u.id, action), "POST", body);
      if (outcome.ok) {
        setTo("");
        setNote("");
        setReason("");
        setMode(null);
        setNotice(success);
        return router.refresh();
      }
      const moved = stageChanged(outcome.detail) !== null ? `${(outcome.detail as { message: string }).message}. Check the stage and try again.` : null;
      const conflict = moved ?? lostConflict(outcome.detail);
      if (conflict !== null) { // someone else changed it: show the page as it is now and say why; the note / reason stay typed
        setTo("");
        setMode(null);
        setFailure(conflict);
        return router.refresh();
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
    void send(mode === "lost" ? "lost" : "reopen", { reason }, mode === "lost" ? "Marked lost." : "Reopened.");
  }
  const openFlag = () => {
    setMode(p.lost ? "reopen" : "lost");
    focus(id("reason"));
  };
  const cancelFlag = () => {
    setMode(null);
    setReason("");
    focus(id("flag"));
  };
  const fieldError = (field: string) => (errors[field] ? <p id={id(`${field}-error`)} className="form-error">{errors[field]}</p> : null);

  return (
    <section className="action-card wide" aria-labelledby={id("heading")}>
      <h3 id={id("heading")}>Partnership stage</h3>
      <p className="muted" style={{ marginTop: 0 }}>Kanban column: {p.column_label}</p>
      {p.lost && (
        <p className="form-message" style={{ whiteSpace: "pre-line" }}>
          Marked lost on {formatDate(p.lost.at)}: {p.lost.reason}
        </p>
      )}
      <ol className="jny-steps" aria-label="Partnership stages">
        {p.stages.map((s, i) => {
          const state: State = i < current ? "done" : i === current ? "current" : "upcoming";
          return (
            <li key={s.key} className={`jny-step jny-${state}`} aria-current={state === "current" ? "step" : undefined}>
              <span className="jny-glyph" aria-hidden="true">{GLYPH[state]}</span>
              <span className="jny-name">{s.label}</span>
              <span className="jny-state">{STATE_TEXT[state]}</span>
            </li>
          );
        })}
      </ol>
      {notice && <p className="form-message" role="status">{notice}</p>}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {canMove && !p.lost && mode === null && (
        <form className="form-grid" onSubmit={submitMove} aria-label="Move stage" style={{ alignItems: "start" }}>
          <div className="field">
            <label htmlFor={id("to")}>Move to</label>
            <select id={id("to")} value={to} onChange={(e) => setTo(e.target.value)} required aria-describedby={errors.to_stage ? id("to_stage-error") : undefined}>
              <option value="">Choose a stage</option>
              {p.stages.map((s) => (
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
      {canFlag && mode === null && (
        <button id={id("flag")} type="button" className="btn secondary small" onClick={openFlag} disabled={busy} style={{ justifySelf: "start" }}>
          {p.lost ? "Reopen" : "Mark lost"}
        </button>
      )}
      {canFlag && mode !== null && (
        <form className="form-grid" onSubmit={submitFlag} aria-label={mode === "lost" ? "Mark lost" : "Reopen"} style={{ alignItems: "start" }}>
          <div className="field">
            <label htmlFor={id("reason")}>Reason</label>
            <textarea id={id("reason")} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} rows={2} required aria-describedby={errors.reason ? id("reason-error") : undefined} />
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

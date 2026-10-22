"use client";

import { FormEvent, useRef, useState } from "react";
import { sendJson } from "@/lib/apiErrors";
import { stageLabel } from "@/lib/agentApplications";
import { subStatusChoices, subStatusLabel } from "@/lib/applicationSubStatus";

type Props = {
  id: string;
  url: string;
  stage: string;
  current: string | null | undefined;
  maxStage?: string;
  onSaved: (data: Record<string, unknown>, message: string) => void;
  onFailed: (message: string, status?: number) => void;
  onCancel?: () => void; // QA-03: a form opened from a toggle can be closed without saving
};

// ccrm-014 (DEC-SCOPE-238): pick a sub-status of this stage or a later one (a later one advances the stage). The server is the
// authority on the forward rule and each role's cap; this only keeps the choices to the ones it accepts.
export default function ApplicationSubStatusForm({ id, url, stage, current, maxStage, onSaved, onFailed, onCancel }: Props) {
  const groups = subStatusChoices(stage, current, maxStage);
  const options = groups.flatMap((group) => group.options);
  const [picked, setPicked] = useState("");
  const target = options.includes(picked) ? picked : (options[0] ?? ""); // after a save the saved value leaves the list
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a same-tick second submit sends nothing

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || !target) return;
    inFlight.current = true;
    setBusy(true);
    let outcome: Awaited<ReturnType<typeof sendJson>>;
    try {
      outcome = await sendJson(url, "POST", { sub_status: target, notes: notes.trim() || null });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
    if (!outcome.ok) return onFailed(outcome.message, outcome.status);
    setNotes("");
    onSaved(outcome.data, `Sub-status updated to ${subStatusLabel(target)}.`);
  }

  if (!groups.length) return null;
  return (
    <form className="form" onSubmit={submit} aria-label="Change sub-status">
      <div className="field">
        <label htmlFor={`sub-status-${id}`}>Sub-status</label>
        <select id={`sub-status-${id}`} value={target} onChange={(event) => setPicked(event.target.value)}>
          {groups.map((group) => (
            <optgroup key={group.stage} label={stageLabel(group.stage)}>
              {group.options.map((option) => (
                <option key={option} value={option}>
                  {subStatusLabel(option)}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`sub-status-notes-${id}`}>Sub-status note (optional)</label>
        <textarea id={`sub-status-notes-${id}`} value={notes} maxLength={2000} onChange={(event) => setNotes(event.target.value)} />
      </div>
      <div className="actions">
        <button className="btn small" disabled={busy || !target}>
          {busy ? "Updating…" : "Update sub-status"}
        </button>
        {onCancel && (
          <button type="button" className="btn ghost small" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

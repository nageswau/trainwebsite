"use client";

import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { sendJson } from "@/lib/apiErrors";
import { AgentApplicationDetail, APPLICATIONS_URL, canWithdraw, nextStages, stageLabel } from "@/lib/agentApplications";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Props = { detail: AgentApplicationDetail; onSaved: (d: AgentApplicationDetail, message: string) => void; onFailed: (message: string, status?: number) => void };

// AGN-008 A4: forward to a later stage (up to status tracking) or withdraw; the displayed status travels as `expected_status`, so a
// stale screen gets the server's 409 instead of acting on an application someone else just changed.
export default function AgentApplicationStatusForm({ detail, onSaved, onFailed }: Props) {
  const options = nextStages(detail.status);
  const [target, setTarget] = useState(options[0] ?? "");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const inFlight = useRef(false); // QA8-06: a same-tick second click / submit sends nothing
  // Keep keyboard users where they were once the confirmation closes by Escape / Keep / a failed withdraw (not after a success).
  const focusAfter = useFocusAfterRender();
  const withdrawId = `withdraw-${detail.id}`;

  async function send(to: string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    let outcome: Awaited<ReturnType<typeof sendJson>>;
    try {
      outcome = await sendJson(`${APPLICATIONS_URL}/${detail.id}/status`, "POST", { to_status: to, expected_status: detail.status, notes: notes.trim() || null });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
    if (!outcome.ok && to === "withdrawn") focusAfter(withdrawId); // a failed withdraw: back to the button, if it still renders
    setConfirming(false);
    if (!outcome.ok) return onFailed(outcome.message, outcome.status);
    const next = (outcome.data as { application?: AgentApplicationDetail }).application;
    if (!next) return onFailed("The change could not be confirmed. Reload to see the current status.");
    setNotes("");
    onSaved(next, to === "withdrawn" ? "Application withdrawn." : `Status updated to ${stageLabel(to)}.`);
  }

  function cancelConfirm() {
    focusAfter(withdrawId);
    setConfirming(false);
  }

  if (!options.length && !canWithdraw(detail.status)) return null;
  return (
    <div>
      <h5>Change status</h5>
      {options.length > 0 && (
        <form className="form" onSubmit={(event: FormEvent) => (event.preventDefault(), send(target))}>
          <div className="field">
            <label htmlFor={`move-${detail.id}`}>Move to</label>
            <select id={`move-${detail.id}`} value={target} onChange={(event) => setTarget(event.target.value)}>
              {options.map((stage) => (
                <option key={stage} value={stage}>
                  {stageLabel(stage)}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={`notes-${detail.id}`}>Note (optional)</label>
            <textarea id={`notes-${detail.id}`} value={notes} maxLength={2000} onChange={(event) => setNotes(event.target.value)} />
          </div>
          <button className="btn small" disabled={busy || !target}>
            {busy ? "Updating…" : "Update status"}
          </button>
        </form>
      )}
      {canWithdraw(detail.status) &&
        (confirming ? (
          <div role="group" aria-label="Confirm withdrawal" onKeyDown={(event: KeyboardEvent) => event.key === "Escape" && cancelConfirm()} style={{ marginTop: 12 }}>
            <p>Withdraw this application? This cannot be undone.</p>
            <div className="actions">
              <button type="button" className="btn small" disabled={busy} onClick={() => send("withdrawn")} autoFocus>
                Yes, withdraw
              </button>
              <button type="button" className="btn ghost small" onClick={cancelConfirm}>
                Keep application
              </button>
            </div>
          </div>
        ) : (
          <button id={withdrawId} type="button" className="btn ghost small" style={{ marginTop: 12 }} onClick={() => setConfirming(true)}>
            Withdraw application
          </button>
        ))}
    </div>
  );
}

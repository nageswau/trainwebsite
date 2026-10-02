"use client";

import { FormEvent, useState } from "react";
import { sendJson } from "@/lib/apiErrors";
import { ReviewDecision, reviewUrl } from "@/lib/agentDocuments";

const LABELS: Record<ReviewDecision, string> = { verified: "Verified", rejected: "Rejected", changes_required: "Changes required" };

// AGN-009 (DEC-SCOPE-051 G1/G2 on DEC-SCOPE-044 P1/P6): a Master picks one of three decisions and gives a reason to reject or ask for
// changes; staff with Verify get one "Mark verified" button. The server enforces both; `required` only saves a round trip.
export default function AgentDocumentReviewForm({ id, name, decisions, onDone }: { id: string; name: string; decisions: ReviewDecision[]; onDone: (message: string, failed: boolean, status?: number) => void }) {
  const [decision, setDecision] = useState<ReviewDecision>(decisions[0]);
  const [busy, setBusy] = useState(false);
  const single = decisions.length === 1;
  const needsReason = decision !== "verified";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const notes = String(new FormData(event.currentTarget).get("notes") ?? "").trim();
    setBusy(true);
    const outcome = await sendJson(reviewUrl(id), "PATCH", { verification_status: decision, notes: notes || null });
    setBusy(false);
    if (!outcome.ok) return onDone(outcome.status !== undefined && outcome.status >= 500 ? "The server couldn't complete this. Please try again in a moment." : outcome.message, true, outcome.status);
    onDone(`${name}: ${LABELS[decision].toLowerCase()}.`, false);
  }

  return (
    <form className="form" aria-label={`Review ${name}`} onSubmit={submit} style={{ marginTop: 12 }}>
      {!single && (
        <div className="field">
          <label htmlFor={`decision-${id}`}>Decision</label>
          <select id={`decision-${id}`} value={decision} onChange={(e) => setDecision(e.target.value as ReviewDecision)}>
            {decisions.map((d) => (
              <option key={d} value={d}>
                {LABELS[d]}
              </option>
            ))}
          </select>
        </div>
      )}
      {!single && (
        <div className="field">
          <label htmlFor={`notes-${id}`}>{needsReason ? "Reason (required)" : "Note (optional)"}</label>
          <textarea id={`notes-${id}`} name="notes" required={needsReason} maxLength={2000} />
        </div>
      )}
      <div className="actions">
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : single ? "Mark verified" : "Save decision"}
        </button>
      </div>
    </form>
  );
}

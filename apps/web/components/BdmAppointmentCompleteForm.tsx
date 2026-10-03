"use client";
import { type FormEvent, useState } from "react";

import type { BdmType } from "@/lib/bdm";
import { appointmentOutcomes, OUTCOME_LABEL, todayIst } from "@/lib/bdmAppointments";

// bdm-006 (A1, A8): the minimal outcome Completed requires, from the BDM type's list, and an optional next follow-up date (today or later,
// India calendar). bdm-007 adds the full meeting report.
export default function BdmAppointmentCompleteForm({ bdmType, busy, onSubmit, onCancel }: { bdmType: BdmType; busy: boolean; onSubmit: (body: { outcome: string; next_follow_up_on: string | null }) => void; onCancel: () => void }) {
  const [outcome, setOutcome] = useState("");
  const [followUp, setFollowUp] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (outcome) onSubmit({ outcome, next_follow_up_on: followUp || null });
  };
  return (
    <form aria-label="Complete appointment" className="action-card" onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="field">
        <label htmlFor="complete-outcome">Outcome (required)</label>
        <select id="complete-outcome" autoFocus required aria-required="true" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
          <option value="">Choose an outcome</option>
          {appointmentOutcomes(bdmType).map((o) => (
            <option key={o} value={o}>
              {OUTCOME_LABEL[o]}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="complete-follow-up">Next follow-up (IST date)</label>
        <input id="complete-follow-up" type="date" min={todayIst()} value={followUp} onChange={(e) => setFollowUp(e.target.value)} />
      </div>
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || !outcome}>
          {busy ? "Saving…" : "Mark completed"}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

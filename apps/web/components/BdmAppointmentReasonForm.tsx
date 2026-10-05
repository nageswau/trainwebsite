"use client";
import { type FormEvent, useId, useState } from "react";

// bdm-006 (A2, R-F6, R-F7): the reason a cancel or no-show needs. The textarea takes focus; Escape cancels; an empty reason is caught here
// as well as by the API (422).
export default function BdmAppointmentReasonForm({ label, submitText, busyText, busy, onSubmit, onCancel }: { label: string; submitText: string; busyText: string; busy: boolean; onSubmit: (reason: string) => void; onCancel: () => void }) {
  const [reason, setReason] = useState("");
  const [missing, setMissing] = useState(false);
  const id = useId();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!reason.trim()) return setMissing(true);
    onSubmit(reason.trim());
  };
  return (
    <form aria-label={label} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="field">
        <label htmlFor={id}>Reason (required)</label>
        <textarea id={id} autoFocus required aria-required="true" maxLength={500} rows={3} value={reason} aria-invalid={missing} aria-describedby={`${id}-hint`} onChange={(e) => { setReason(e.target.value); setMissing(false); }} />
        <p id={`${id}-hint`} className={missing ? "form-error" : "muted"} style={{ margin: 0 }}>
          {missing ? "Enter a reason." : `${reason.length}/500`}
        </p>
      </div>
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>
          {busy ? busyText : submitText}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel}>
          Keep it
        </button>
      </div>
    </form>
  );
}

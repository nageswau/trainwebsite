"use client";
import { type FormEvent, useState } from "react";

import BdmOverlapAlert from "@/components/BdmOverlapAlert";
import { type Appointment, DURATIONS, formatMinutes, isoToIstInput, istInputToIso, nowIstInput, type Overlap } from "@/lib/bdmAppointments";

type Body = { starts_at: string; duration_minutes: number; reason: string | null };

// bdm-006 (AC4): a new future time (IST), optionally a new duration and a reason. The old time is kept in the history by the API.
export default function BdmAppointmentRescheduleForm({ appointment, busy, warning, onSubmit, onCancel }: { appointment: Appointment; busy: boolean; warning: Overlap | null; onSubmit: (body: Body, confirm: boolean) => void; onCancel: () => void }) {
  const [when, setWhen] = useState(isoToIstInput(appointment.starts_at));
  const [duration, setDuration] = useState(appointment.duration_minutes);
  const [reason, setReason] = useState("");
  const body = (): Body => ({ starts_at: istInputToIso(when), duration_minutes: duration, reason: reason.trim() || null });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit(body(), false);
  };
  const durations = DURATIONS.includes(duration) ? DURATIONS : [...DURATIONS, duration].sort((a, b) => a - b);
  return (
    <form aria-label="Reschedule appointment" className="action-card" onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="field">
        <label htmlFor={`resched-${appointment.id}`}>New date and time (IST) (required)</label>
        <input id={`resched-${appointment.id}`} type="datetime-local" autoFocus required aria-required="true" min={nowIstInput()} value={when} onChange={(e) => setWhen(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor={`resched-dur-${appointment.id}`}>Duration</label>
        <select id={`resched-dur-${appointment.id}`} value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
          {durations.map((d) => (
            <option key={d} value={d}>
              {formatMinutes(d)}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`resched-why-${appointment.id}`}>Reason</label>
        <textarea id={`resched-why-${appointment.id}`} maxLength={500} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      {warning && <BdmOverlapAlert overlap={warning} busy={busy} onConfirm={() => onSubmit(body(), true)} onCancel={onCancel} />}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || warning !== null}>
          {busy ? "Saving…" : "Save new time"}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

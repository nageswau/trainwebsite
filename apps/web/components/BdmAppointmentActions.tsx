"use client";
import { useState } from "react";

import BdmAppointmentCompleteForm from "@/components/BdmAppointmentCompleteForm";
import BdmAppointmentReasonForm from "@/components/BdmAppointmentReasonForm";
import BdmAppointmentRescheduleForm from "@/components/BdmAppointmentRescheduleForm";
import { sendJson } from "@/lib/apiErrors";
import type { BdmType } from "@/lib/bdm";
import { type Appointment, APPOINTMENTS_URL, isAppointmentBody, type Overlap, overlap as readOverlap, STATUS_LABEL } from "@/lib/bdmAppointments";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Group = "reschedule" | "cancel" | "no_show" | "complete";
const DONE: Record<string, string> = { confirm: "Appointment confirmed.", reschedule: "Appointment rescheduled.", cancel: "Appointment cancelled.", "no-show": "Marked as a no-show.", complete: "Appointment completed." };

// bdm-006 (spec §6.2, R-F4, R-F7): the status actions, from `permissions` only (the API enforces every rule). One inline group is open
// at a time; Escape or Cancel closes it and focus returns to its button. A 409 means the appointment changed elsewhere: refetch and say so.
export default function BdmAppointmentActions({ appointment, bdmType, onChanged }: { appointment: Appointment; bdmType: BdmType | null; onChanged: (a: Appointment, text: string) => void }) {
  const [open, setOpen] = useState<Group | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [warning, setWarning] = useState<Overlap | null>(null);
  const focus = useFocusAfterRender();
  const p = appointment.permissions;
  const buttonId = (g: string) => `appt-${appointment.id}-${g}`;
  if (!Object.values(p).some(Boolean)) return null;

  const close = (g: Group) => {
    setOpen(null);
    setWarning(null);
    focus(buttonId(g));
  };
  async function refetch(): Promise<Appointment | null> {
    const response = await fetch(`${APPOINTMENTS_URL}/${appointment.id}`).catch(() => null);
    const body = response?.ok ? await response.json().catch(() => null) : null;
    return isAppointmentBody(body) ? body.appointment : null;
  }
  async function act(path: string, body: Record<string, unknown> = {}) {
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(`${APPOINTMENTS_URL}/${appointment.id}/${path}`, "POST", body);
    setBusy(false);
    if (outcome.ok && isAppointmentBody(outcome.data)) {
      setOpen(null);
      setWarning(null);
      return onChanged(outcome.data.appointment, DONE[path]);
    }
    if (!outcome.ok && outcome.status === 409) {
      const clash = readOverlap(outcome.detail);
      if (clash) return setWarning(clash);
      const fresh = await refetch();
      if (fresh) {
        setOpen(null);
        return onChanged(fresh, `This appointment changed — it is now ${STATUS_LABEL[fresh.status]}.`);
      }
    }
    setFailure(outcome.ok ? "Unable to update this appointment." : outcome.message);
  }
  const toggle = (g: Group) => {
    setFailure(null);
    setWarning(null);
    setOpen(open === g ? null : g);
  };

  return (
    <section className="action-card wide" aria-label="Actions">
      <div className="actions">
        {p.can_confirm && (
          <button id={buttonId("confirm")} type="button" className="btn small" disabled={busy} onClick={() => void act("confirm")}>
            {busy && !open ? "Confirming…" : "Confirm"}
          </button>
        )}
        {p.can_reschedule && (
          <button id={buttonId("reschedule")} type="button" className="btn secondary small" disabled={busy} aria-expanded={open === "reschedule"} onClick={() => toggle("reschedule")}>
            Reschedule
          </button>
        )}
        {p.can_complete && bdmType && (
          <button id={buttonId("complete")} type="button" className="btn secondary small" disabled={busy} aria-expanded={open === "complete"} onClick={() => toggle("complete")}>
            Complete
          </button>
        )}
        {p.can_no_show && (
          <button id={buttonId("no_show")} type="button" className="btn secondary small" disabled={busy} aria-expanded={open === "no_show"} onClick={() => toggle("no_show")}>
            Mark no-show
          </button>
        )}
        {p.can_cancel && (
          <button id={buttonId("cancel")} type="button" className="btn secondary small" disabled={busy} aria-expanded={open === "cancel"} onClick={() => toggle("cancel")}>
            Cancel appointment
          </button>
        )}
      </div>
      {open === "reschedule" && (
        <BdmAppointmentRescheduleForm appointment={appointment} busy={busy} warning={warning} onEdit={() => setWarning(null)} onDismissWarning={() => setWarning(null)} onSubmit={(body, confirm) => void act("reschedule", { ...body, confirm_overlap: confirm })} onCancel={() => close("reschedule")} />
      )}
      {open === "complete" && bdmType && <BdmAppointmentCompleteForm bdmType={bdmType} busy={busy} onSubmit={(body) => void act("complete", body)} onCancel={() => close("complete")} />}
      {open === "cancel" && <BdmAppointmentReasonForm label="Cancel appointment" submitText="Yes, cancel it" busyText="Cancelling…" busy={busy} onSubmit={(reason) => void act("cancel", { reason })} onCancel={() => close("cancel")} />}
      {open === "no_show" && <BdmAppointmentReasonForm label="Mark as no-show" submitText="Mark no-show" busyText="Saving…" busy={busy} onSubmit={(reason) => void act("no-show", { reason })} onCancel={() => close("no_show")} />}
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
    </section>
  );
}

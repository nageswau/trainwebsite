"use client";
import { useState } from "react";

import BdmAppointmentReasonForm from "@/components/BdmAppointmentReasonForm";
import BdmAppointmentRescheduleForm from "@/components/BdmAppointmentRescheduleForm";
import BdmMeetingReportForm from "@/components/BdmMeetingReportForm";
import { sendJson } from "@/lib/apiErrors";
import type { BdmType } from "@/lib/bdm";
import { type Appointment, APPOINTMENTS_URL, isAppointmentBody, type Overlap, overlap as readOverlap, STATUS_LABEL } from "@/lib/bdmAppointments";
import { fieldErrors } from "@/lib/bdmTravel";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Group = "reschedule" | "cancel" | "no_show" | "complete";
const DONE: Record<string, string> = { confirm: "Appointment confirmed.", reschedule: "Appointment rescheduled.", cancel: "Appointment cancelled.", "no-show": "Marked as a no-show.", complete: "Appointment completed." };
// bdm-007 (Review Focus 5): a report that could not be saved stays on screen with this, never thrown away by a refetch.
const CHANGED_ELSEWHERE = "This appointment changed elsewhere — copy your notes, then reload.";

// bdm-006 (spec §6.2, R-F4, R-F7): the status actions, from `permissions` only (the API enforces every rule). One inline group is open
// at a time; Escape or Cancel closes it and focus returns to its button. A 409 means the appointment changed elsewhere: refetch and say so.
export default function BdmAppointmentActions({ appointment, bdmType, onChanged }: { appointment: Appointment; bdmType: BdmType | null; onChanged: (a: Appointment, text: string) => void }) {
  const [open, setOpen] = useState<Group | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [fieldErrs, setFieldErrs] = useState<Record<string, string>>({});
  // The warning keeps the body that was checked: "Save anyway" resends it, never the form's current values.
  const [warning, setWarning] = useState<{ overlap: Overlap; path: string; body: Record<string, unknown> } | null>(null);
  const focus = useFocusAfterRender();
  const p = appointment.permissions;
  const buttonId = (g: string) => `appt-${appointment.id}-${g}`;
  const failureId = buttonId("failure");
  // QA7-01: the report's Edit button lives in BdmMeetingReportSection, so `can_edit_report` alone is no reason for this bar.
  if (!Object.entries(p).some(([key, allowed]) => allowed && key !== "can_edit_report")) return null;

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
    setFieldErrs({});
    const outcome = await sendJson(`${APPOINTMENTS_URL}/${appointment.id}/${path}`, "POST", body);
    setBusy(false);
    if (outcome.ok && isAppointmentBody(outcome.data)) {
      setOpen(null);
      setWarning(null);
      return onChanged(outcome.data.appointment, DONE[path]);
    }
    if (!outcome.ok && path === "complete") {
      if (outcome.status === 409) {
        setFailure(CHANGED_ELSEWHERE);
        return focus(failureId);
      }
      const mapped = fieldErrors(outcome.detail);
      if (Object.keys(mapped).length) {
        setFieldErrs(mapped);
        return setFailure("Check the highlighted fields.");
      }
    }
    if (!outcome.ok && outcome.status === 409) {
      const clash = readOverlap(outcome.detail);
      if (clash) return setWarning({ overlap: clash, path, body });
      const fresh = await refetch();
      if (fresh) {
        setOpen(null);
        return onChanged(fresh, `This appointment changed — it is now ${STATUS_LABEL[fresh.status]}.`);
      }
    }
    const server = !outcome.ok && (outcome.status ?? 0) >= 500;
    setFailure(outcome.ok ? "Unable to update this appointment." : server ? "We couldn't update the appointment. Please try again." : outcome.message);
  }
  async function reload() {
    const fresh = await refetch();
    if (!fresh) return setFailure("Unable to load this appointment. Reload the page.");
    setFailure(null);
    setOpen(null);
    onChanged(fresh, `This appointment is now ${STATUS_LABEL[fresh.status]}.`);
  }
  const toggle = (g: Group) => {
    setFailure(null);
    setFieldErrs({});
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
        <BdmAppointmentRescheduleForm appointment={appointment} busy={busy} warning={warning?.overlap ?? null} onEdit={() => setWarning(null)} onDismissWarning={() => setWarning(null)} onSubmit={(body) => void act("reschedule", { ...body, confirm_overlap: false })} onConfirm={() => warning && void act(warning.path, { ...warning.body, confirm_overlap: true })} onCancel={() => close("reschedule")} />
      )}
      {open === "complete" && bdmType && <BdmMeetingReportForm bdmType={bdmType} mode="complete" busy={busy} errors={fieldErrs} onSubmit={(body) => void act("complete", body)} onCancel={() => close("complete")} />}
      {open === "cancel" && <BdmAppointmentReasonForm label="Cancel appointment" submitText="Yes, cancel it" busyText="Cancelling…" busy={busy} onSubmit={(reason) => void act("cancel", { reason })} onCancel={() => close("cancel")} />}
      {open === "no_show" && <BdmAppointmentReasonForm label="Mark as no-show" submitText="Mark no-show" busyText="Saving…" busy={busy} onSubmit={(reason) => void act("no-show", { reason })} onCancel={() => close("no_show")} />}
      {failure && (
        <p id={failureId} tabIndex={-1} className="form-error" role="alert">
          {failure}
        </p>
      )}
      {failure === CHANGED_ELSEWHERE && (
        <button type="button" className="btn secondary small" onClick={() => void reload()}>
          Reload
        </button>
      )}
    </section>
  );
}

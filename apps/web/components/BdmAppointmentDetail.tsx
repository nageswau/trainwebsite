"use client";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";

import BdmAppointmentActions from "@/components/BdmAppointmentActions";
import BdmAppointmentForm from "@/components/BdmAppointmentForm";
import BdmAppointmentHistory from "@/components/BdmAppointmentHistory";
import BdmMeetingReportSection from "@/components/BdmMeetingReportSection";
import type { BdmType } from "@/lib/bdm";
import { type Appointment, type AppointmentTrip, formatInr, type ReminderAction, STATUS_CLASS, STATUS_LABEL, TYPE_LABEL, whenText } from "@/lib/bdmAppointments";
import { display, LINK_STYLE } from "@/lib/bdmOrganizations";
import { tripPagePath, type TripRow } from "@/lib/bdmTravel";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl style={{ display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "8px 16px", margin: 0 }}>
      {rows.map(([label, value]) => [
        <dt key={`${label}-t`} className="muted">
          {label}
        </dt>,
        <dd key={`${label}-d`} style={{ margin: 0, overflowWrap: "anywhere" }}>
          {value}
        </dd>,
      ])}
    </dl>
  );
}

// bdm-011: the linked trip, opening on its appointments; it says when the trip can't be relied on yet (Q-05) or was cancelled (L4).
function TripCell({ trip, view }: { trip: AppointmentTrip; view: "owner" | "manager" }) {
  const note = trip.travel_status === "cancelled" ? "Trip cancelled" : trip.approval_status !== "approved" ? "Trip not approved yet" : null;
  return (
    <>
      <Link href={`${tripPagePath(view, trip.id)}#trip-appointments`} style={LINK_STYLE}>
        {trip.code} · {trip.from_place} → {trip.to_place}
      </Link>
      {note && <span className="muted"> · {note}</span>}
    </>
  );
}

const DONE_WORD: Record<ReminderAction, string> = { confirm: "confirmed", reschedule: "rescheduled", cancel: "cancelled" };

// bdm-012 (DEC-SCOPE-102 R10): what a reminder button's action means for this appointment now.
function reminderNotice(appt: Appointment, action: ReminderAction): string | null {
  if (appt.permissions[`can_${action}`]) return action === "confirm" ? "Check the details, then select Confirm." : null;
  if (action === "confirm" && appt.status === "confirmed") return "This appointment is already confirmed.";
  return `This appointment is ${STATUS_LABEL[appt.status]}, so it can no longer be ${DONE_WORD[action]}.`;
}

// bdm-006 (spec §6.2, §12.2): one appointment. Every write re-renders from the appointment the API returns. Actions render from
// `permissions` only; a manager (bdmType null) sees no actions. bdm-012: `action` (a reminder button) opens that action once.
export default function BdmAppointmentDetail({ initial, basePath, bdmType, created = false, action = null, trips, tripsUnavailable }: {
  initial: Appointment; basePath: string; bdmType: BdmType | null; created?: boolean; action?: ReminderAction | null; trips?: TripRow[]; tripsUnavailable?: boolean;
}) {
  const [appt, setAppt] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState<string | null>(created ? `Appointment ${initial.code} booked.` : action && reminderNotice(initial, action));
  const focus = useFocusAfterRender();
  const statusId = `appt-${appt.id}-status`;
  const editId = `appt-${appt.id}-edit`;
  useEffect(() => {
    if (created || action) window.history.replaceState(null, "", `${basePath}/${initial.id}`);
  }, [created, action, basePath, initial.id]);
  const manager = basePath.startsWith("/bdm/manager");
  const orgHref = `${manager ? "/bdm/manager/organizations" : "/bdm/organizations"}/${appt.organization.id}`;
  const changed = (next: Appointment, text: string) => {
    setAppt(next);
    setNotice(text);
    focus(statusId);
  };
  const p = appt.permissions;
  const showEditor = editing && p.can_edit && bdmType;

  const rows: [string, ReactNode][] = [
    ["Date & time", whenText(appt.starts_at, appt.duration_minutes)],
    ["Organization", <Link key="org" href={orgHref} style={LINK_STYLE}>{appt.organization.name}</Link>],
    ["Contact person", appt.contact_name],
    ["Designation", display(appt.contact_designation)],
    ["Mobile", display(appt.contact_phone)],
    ["Email", display(appt.contact_email)],
    ["Type", TYPE_LABEL[appt.appointment_type] ?? appt.appointment_type],
    ["Location", display(appt.location)],
    ["Purpose", display(appt.purpose)],
    ["Remarks", display(appt.remarks)],
    ["Expected leads", display(appt.expected_leads)],
    ["Expected revenue", formatInr(appt.expected_revenue)],
    ["BDM", `${appt.bdm.full_name}${appt.bdm.active ? "" : " (inactive)"}`],
    ["Trip", appt.trip ? <TripCell key="trip" trip={appt.trip} view={manager ? "manager" : "owner"} /> : display(null)],
  ];

  return (
    <>
      <div className="portal-title" style={{ flexWrap: "wrap", gap: 12 }}>
        <div>
          <div className="eyebrow">
            {appt.code} · {TYPE_LABEL[appt.appointment_type] ?? appt.appointment_type}
          </div>
          <h2>
            {appt.organization.name} <span className={STATUS_CLASS[appt.status]}>{STATUS_LABEL[appt.status]}</span>{" "}
            {appt.organization.archived && <span className="badge">Archived</span>}{" "}
            {appt.outcome_pending && <span className="badge">Outcome pending</span>}
          </h2>
          <p style={{ margin: 0 }}>
            <Link href={basePath} style={LINK_STYLE}>
              Back to appointments
            </Link>
          </p>
        </div>
        <div className="actions">
          {p.can_edit && bdmType && !showEditor && (
            <button id={editId} type="button" className="btn secondary small" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
        </div>
      </div>
      <div id={statusId} tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>
        {notice}
      </div>
      {p.can_complete && (
        <p className="muted" role="note">
          Outcome pending — file the meeting report, or mark it as a no-show.
        </p>
      )}
      {appt.outcome_pending && !p.can_complete && (
        <p className="muted" role="note">
          Outcome pending — the BDM hasn&apos;t filed the meeting report yet.
        </p>
      )}
      {showEditor ? (
        <section className="action-card wide" aria-label="Edit details">
          <h3>Edit details</h3>
          <BdmAppointmentForm
            mode="edit"
            bdmType={bdmType}
            appointment={appt}
            trips={trips}
            tripsUnavailable={tripsUnavailable}
            onSaved={(a, saved) => {
              setEditing(false);
              changed(a, saved ? "Changes saved." : "No changes to save.");
            }}
            onCancel={() => {
              setEditing(false);
              focus(editId);
            }}
          />
        </section>
      ) : (
        <section className="action-card wide" aria-label="Details">
          <h3>Details</h3>
          <Rows rows={rows} />
        </section>
      )}
      <BdmMeetingReportSection appointment={appt} bdmType={bdmType} onChanged={changed} />
      {!showEditor && <BdmAppointmentActions appointment={appt} bdmType={bdmType} onChanged={changed} initialAction={action && initial.permissions[`can_${action}`] ? action : null} />}
      <BdmAppointmentHistory events={appt.events} />
    </>
  );
}

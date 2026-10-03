"use client";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";

import BdmAppointmentActions from "@/components/BdmAppointmentActions";
import BdmAppointmentForm from "@/components/BdmAppointmentForm";
import BdmAppointmentHistory from "@/components/BdmAppointmentHistory";
import type { BdmType } from "@/lib/bdm";
import { type Appointment, formatInr, OUTCOME_LABEL, STATUS_CLASS, STATUS_LABEL, TYPE_LABEL, whenText } from "@/lib/bdmAppointments";
import { display, LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatCalendarDate } from "@/lib/formatDate";
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

// bdm-006 (spec §6.2, §12.2): one appointment. Every write re-renders from the appointment the API returns. Actions render from
// `permissions` only; a manager (bdmType null) sees no actions.
export default function BdmAppointmentDetail({ initial, basePath, bdmType, created = false }: { initial: Appointment; basePath: string; bdmType: BdmType | null; created?: boolean }) {
  const [appt, setAppt] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState<string | null>(created ? `Appointment ${initial.code} booked.` : null);
  const focus = useFocusAfterRender();
  const statusId = `appt-${appt.id}-status`;
  const editId = `appt-${appt.id}-edit`;
  useEffect(() => {
    if (created) window.history.replaceState(null, "", `${basePath}/${initial.id}`);
  }, [created, basePath, initial.id]);
  const orgHref = `${basePath.startsWith("/bdm/manager") ? "/bdm/manager/organizations" : "/bdm/organizations"}/${appt.organization.id}`;
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
            {appt.organization.archived && <span className="badge">Archived</span>}
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
          The start time has passed — complete it or mark it as a no-show.
        </p>
      )}
      {showEditor ? (
        <section className="action-card wide" aria-label="Edit details">
          <h3>Edit details</h3>
          <BdmAppointmentForm
            mode="edit"
            bdmType={bdmType}
            appointment={appt}
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
      {appt.status === "completed" && (
        <section className="action-card wide" aria-label="Outcome">
          <h3>Outcome</h3>
          <Rows rows={[["Outcome", OUTCOME_LABEL[appt.outcome ?? ""] ?? display(appt.outcome)], ["Next follow-up", appt.next_follow_up_on ? formatCalendarDate(appt.next_follow_up_on) : "—"]]} />
        </section>
      )}
      {!showEditor && <BdmAppointmentActions appointment={appt} bdmType={bdmType} onChanged={changed} />}
      <BdmAppointmentHistory events={appt.events} />
    </>
  );
}

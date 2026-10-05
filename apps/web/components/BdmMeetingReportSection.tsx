"use client";
import Link from "next/link";
import { useState } from "react";

import BdmMeetingReportForm from "@/components/BdmMeetingReportForm";
import { sendJson } from "@/lib/apiErrors";
import type { BdmType } from "@/lib/bdm";
import { type Appointment, APPOINTMENTS_URL, isAppointmentBody, OUTCOME_LABEL, type ReportBody } from "@/lib/bdmAppointments";
import { display, LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";
import { fieldErrors } from "@/lib/bdmTravel";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere", margin: 0 } as const;

// bdm-007 (spec §8): the filed meeting report. React renders every value as text (no HTML). The author edits it on the IST day it
// was filed (`can_edit_report`; the API decides). A failed save keeps the form and its text.
export default function BdmMeetingReportSection({ appointment: a, bdmType, onChanged }: { appointment: Appointment; bdmType: BdmType | null; onChanged: (a: Appointment, text: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const focus = useFocusAfterRender();
  const r = a.report;
  if (!r) return null;
  const editId = `appt-${a.id}-edit-report`;

  async function save(body: ReportBody) {
    setBusy(true);
    setFailure(null);
    setErrors({});
    const outcome = await sendJson(`${APPOINTMENTS_URL}/${a.id}/report`, "PATCH", body);
    setBusy(false);
    if (outcome.ok && isAppointmentBody(outcome.data)) {
      setEditing(false);
      return onChanged(outcome.data.appointment, "Meeting report saved.");
    }
    const mapped = outcome.ok ? {} : fieldErrors(outcome.detail);
    setErrors(mapped);
    const server = !outcome.ok && (outcome.status ?? 0) >= 500;
    setFailure(Object.keys(mapped).length ? "Check the highlighted fields." : outcome.ok ? "Unable to save the report." : server ? "We couldn't save the report. Please try again — your text is kept." : outcome.message);
  }

  const followUp = a.next_follow_up_on ? formatCalendarDate(a.next_follow_up_on) : "—";
  const rows: [string, string][] = [
    ["Outcome", OUTCOME_LABEL[a.outcome ?? ""] ?? display(a.outcome)],
    ["Discussion", display(r.discussion)],
    ["Requirements", display(r.requirements)],
    ["Opportunity", display(r.opportunity)],
    ["Next action", display(r.next_action)],
    ["Responsible person", display(r.responsible_person)],
    ["Next follow-up", followUp],
    ["Filed", `${r.author.full_name}, ${formatSchoolDateTime(r.submitted_at, true)}`],
  ];
  return (
    <section className="action-card wide" aria-label="Meeting report">
      <h3>Meeting report</h3>
      {r.legacy && <p className="muted">Recorded before meeting reports — outcome only.</p>}
      {editing && bdmType ? (
        <BdmMeetingReportForm bdmType={bdmType} mode="edit" busy={busy} errors={errors} initial={{ outcome: a.outcome, next_follow_up_on: a.next_follow_up_on, report: r }} onSubmit={(body) => void save(body)} onCancel={() => { setEditing(false); setFailure(null); focus(editId); }} />
      ) : (
        <dl style={{ display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "8px 16px", margin: 0 }}>
          {rows.map(([label, value]) => [
            <dt key={`${label}-t`} className="muted">{label}</dt>,
            <dd key={`${label}-d`} style={TEXT}>{value}</dd>,
          ])}
        </dl>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {!editing && (
        <div className="actions">
          {a.permissions.can_edit_report && bdmType && (
            <>
              <button id={editId} type="button" className="btn secondary small" onClick={() => setEditing(true)}>Edit report</button>
              <span className="field-hint">You can change this report until midnight IST today.</span>
            </>
          )}
          {a.outcome === "reschedule" && bdmType && !a.organization.archived && (
            <Link className="btn small" href={`/bdm/appointments/new?organization=${encodeURIComponent(a.organization.id)}`} style={LINK_STYLE}>Book the next meeting</Link>
          )}
        </div>
      )}
    </section>
  );
}

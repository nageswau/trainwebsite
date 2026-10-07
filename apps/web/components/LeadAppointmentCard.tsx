"use client";

import { type FormEvent, useId, useState } from "react";

import { isoToIstInput, istInputToIso, nowIstInput } from "@/lib/bdmAppointments";
import { fieldErrors } from "@/lib/bdmTravel";
import { isRequestBody, sendJson } from "@/lib/apiErrors";
import { formatSchoolDateTime } from "@/lib/formatDate";
import {
  ACTION_LABEL, STATUS_LABEL, actionUrl, clashText, safeLink, whenText, type AppointmentAction, type LeadAppointment,
} from "@/lib/leadAppointments";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Notice = { text: string; failed: boolean } | null;
const STATUS_ACTIONS = [["confirm", "can_confirm"], ["complete", "can_complete"], ["no_show", "can_no_show"]] as const;

/** tel-016 (EVID-019 §9 fields; AP2, AP9, AP10): one lead appointment -- its details, its history and the actions the API says the
 *  viewer may take (`permissions`). Cancel asks for a reason; reschedule for the new IST time. `showLead` is the counselor's view. */
export default function LeadAppointmentCard({ appointment: a, showLead, onChanged }: {
  appointment: LeadAppointment; showLead: boolean; onChanged: (next: LeadAppointment) => void;
}) {
  const idp = useId();
  const focus = useFocusAfterRender();
  const [open, setOpen] = useState<"cancel" | "reschedule" | null>(null);
  const [reason, setReason] = useState("");
  const [when, setWhen] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const link = safeLink(a.meeting_link);
  const p = a.permissions;

  function start(kind: "cancel" | "reschedule") {
    setOpen(kind);
    setNotice(null);
    setFieldError(null);
    setReason("");
    setWhen(kind === "reschedule" ? isoToIstInput(a.scheduled_at) : "");
    focus(`${idp}-${kind}-input`);
  }

  async function act(action: AppointmentAction, body: Record<string, string> = {}) {
    setBusy(true);
    setNotice(null);
    setFieldError(null);
    const outcome = await sendJson(actionUrl(a.id, action), "POST", body);
    setBusy(false);
    if (!outcome.ok) {
      const field = Object.values(fieldErrors(outcome.detail))[0];
      if (field && open) {
        setFieldError(field);
        return focus(`${idp}-${open}-input`);
      }
      return setNotice({ text: clashText(outcome.detail) ?? outcome.message, failed: true });
    }
    if (!isRequestBody(outcome.data)) return setNotice({ text: "Unable to update the appointment.", failed: true });
    setOpen(null);
    const next = outcome.data as unknown as LeadAppointment;
    setNotice({ text: `Appointment ${STATUS_LABEL[next.status].toLowerCase()}.`, failed: false });
    onChanged(next);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (open === "cancel") {
      if (!reason.trim()) {
        setFieldError("Add a reason for cancelling.");
        return focus(`${idp}-cancel-input`);
      }
      return act("cancel", { reason: reason.trim() });
    }
    if (!when) {
      setFieldError("Choose the new date and time.");
      return focus(`${idp}-reschedule-input`);
    }
    return act("reschedule", { scheduled_at: istInputToIso(when), ...(reason.trim() ? { reason: reason.trim() } : {}) });
  }

  // AP13: the counselor sees who the lead is and how to reach them; the lead's own page names the counselor instead
  const who: [string, React.ReactNode][] = showLead
    ? [["Lead", `${a.lead.name} (${a.lead.lead_code})`], ["Mobile", a.lead.phone ?? "—"], ["Email", a.lead.email ?? "—"]]
    : [["Counselor", a.counselor?.full_name ?? "—"]];
  const rows: [string, React.ReactNode][] = [
    ["When", whenText(a.scheduled_at, a.duration_minutes)],
    ...who,
    ["Mode", a.mode],
    ["Meeting link", link ? <a href={link} target="_blank" rel="noopener noreferrer">{link}</a> : a.meeting_link ?? "—"],
    ["Location", a.location ?? "—"],
    ["Purpose", a.purpose ?? "—"],
    ["Remarks", a.remarks ?? "—"],
    ["Booked by", a.booked_by?.full_name ?? "—"],
  ];
  const actions = STATUS_ACTIONS.filter(([, key]) => p[key]);
  const reasonId = open === "cancel" ? `${idp}-cancel-input` : `${idp}-reason-input`; // a cancel's reason is the field focused on error
  return (
    <article className="action-card" aria-labelledby={`${idp}-title`} style={{ display: "grid", gap: 8, padding: 12 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", justifyContent: "space-between" }}>
        <h4 id={`${idp}-title`} style={{ margin: 0 }}>{a.type_label} <span className="muted" style={{ fontWeight: 400 }}>{a.code}</span></h4>
        <span className="badge">{STATUS_LABEL[a.status] ?? a.status}</span>
      </div>
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: "6px 16px", margin: 0 }}>
        {rows.map(([term, value]) => (
          <div key={term}>
            <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
            <dd style={{ margin: 0, overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}>{value}</dd>
          </div>
        ))}
      </dl>
      {(actions.length > 0 || p.can_reschedule || p.can_cancel) && !open && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {actions.map(([action]) => (
            <button key={action} type="button" className="btn small" disabled={busy} onClick={() => act(action)}>{ACTION_LABEL[action]}</button>
          ))}
          {p.can_reschedule && <button type="button" className="btn secondary small" disabled={busy} onClick={() => start("reschedule")}>Reschedule</button>}
          {p.can_cancel && <button type="button" className="btn secondary small" disabled={busy} onClick={() => start("cancel")}>Cancel appointment</button>}
        </div>
      )}
      {open && (
        <form onSubmit={submit} noValidate style={{ display: "grid", gap: 8 }}>
          {open === "reschedule" && (
            <div className="field">
              <label htmlFor={`${idp}-reschedule-input`}>New date and time (IST)</label>
              <input id={`${idp}-reschedule-input`} type="datetime-local" min={nowIstInput()} value={when} disabled={busy} required
                aria-invalid={fieldError ? true : undefined} aria-describedby={fieldError ? `${idp}-error` : undefined} onChange={(e) => { setWhen(e.target.value); setFieldError(null); }} />
            </div>
          )}
          <div className="field">
            <label htmlFor={reasonId}>{open === "cancel" ? "Reason for cancelling" : "Reason (optional)"}</label>
            <textarea id={reasonId} rows={2} maxLength={500} value={reason} disabled={busy}
              aria-invalid={open === "cancel" && fieldError ? true : undefined} aria-describedby={fieldError ? `${idp}-error` : undefined}
              onChange={(e) => { setReason(e.target.value); setFieldError(null); }} />
          </div>
          {fieldError && <p id={`${idp}-error`} className="form-error" style={{ margin: 0 }}>{fieldError}</p>}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : open === "cancel" ? "Cancel appointment" : "Save new time"}</button>
            <button type="button" className="btn secondary small" disabled={busy} onClick={() => setOpen(null)}>Back</button>
          </div>
        </form>
      )}
      {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0, fontSize: 13 }}>{notice.text}</p>}
      <details>
        <summary style={{ cursor: "pointer", fontSize: 13 }}>History ({a.events.length})</summary>
        <ol style={{ margin: "6px 0 0", paddingLeft: 18, display: "grid", gap: 4, fontSize: 13 }}>
          {a.events.map((e, i) => (
            <li key={i}>
              <strong>{e.from_status ? `${STATUS_LABEL[e.from_status]} → ${STATUS_LABEL[e.to_status]}` : "Booked"}</strong>
              {e.old_scheduled_at && e.new_scheduled_at && ` · ${formatSchoolDateTime(e.old_scheduled_at, true)} → ${formatSchoolDateTime(e.new_scheduled_at, true)}`}
              <span className="muted"> · {e.actor_name} · {formatSchoolDateTime(e.created_at, true)}</span>
              {e.reason && <div style={{ overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}>{e.reason}</div>}
            </li>
          ))}
        </ol>
      </details>
    </article>
  );
}

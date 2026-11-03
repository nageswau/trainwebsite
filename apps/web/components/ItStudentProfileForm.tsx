"use client";

import { FormEvent, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { detailMessage, sendJson } from "@/lib/apiErrors";
import { formatCalendarDate } from "@/lib/formatDate";
import { stageTone } from "@/lib/itLifecycle";
import {
  IT_DELIVERY_MODES, IT_PROFILE_FIELD_LABELS, toPatchBody, type ItEnrollment, type ItStudentProfile, type ItStudentProfileResponse,
} from "@/lib/itStudentProfile";

const YEAR_MAX = new Date().getFullYear() + 6;

/** A refused save in words: each 422 item with its field label ("Emergency contact phone: ..."), else the server's own message. */
function refusal(detail: unknown, message: string): string {
  if (!Array.isArray(detail)) return message;
  return detail
    .map((item: { loc?: unknown[] }) => {
      const field = Array.isArray(item?.loc) ? IT_PROFILE_FIELD_LABELS[String(item.loc[item.loc.length - 1])] : undefined;
      return [field, detailMessage([item])].filter(Boolean).join(": ");
    })
    .join("; ");
}

// itc-012 (DEC-SCOPE-345): the IT student record -- personal details and the emergency contact (the student, their IT counselor or the
// IT Admin edit them), then each enrolment's effective dates and mode. With `enrollmentsUrl` (staff only) each enrolment gets an override
// editor; an empty override follows the batch. A second save while one is in flight is ignored; on a refusal the entries stay.
export default function ItStudentProfileForm({ initial, url, enrollmentsUrl }: { initial: ItStudentProfileResponse; url: string; enrollmentsUrl?: string }) {
  const [profile, setProfile] = useState<ItStudentProfile>(initial.profile);
  const [enrollments, setEnrollments] = useState<ItEnrollment[]>(initial.enrollments);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const inFlight = useRef(false);

  const text = (key: keyof ItStudentProfile) => ({
    value: String(profile[key] ?? ""),
    onChange: (e: { target: { value: string } }) => setProfile((p) => ({ ...p, [key]: e.target.value })),
  });

  function saved(data: ItStudentProfileResponse) {
    setProfile(data.profile);
    setEnrollments(data.enrollments);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setSaving(true);
    setMessage(null);
    const outcome = await sendJson(url, "PATCH", toPatchBody(profile));
    inFlight.current = false;
    setSaving(false);
    if (!outcome.ok) return setMessage({ text: refusal(outcome.detail, outcome.message), failed: true });
    saved(outcome.data as ItStudentProfileResponse);
    setMessage({ text: "Details saved.", failed: false });
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <form className="form" onSubmit={submit} aria-label="Student details">
        <p className="muted" style={{ margin: 0 }}>
          {profile.exists && profile.updated_by_name ? (
            <>Last saved by {profile.updated_by_name}{profile.updated_at && <> · <LocalTime value={profile.updated_at} /></>}</>
          ) : (
            "No details saved yet."
          )}
        </p>
        <fieldset className="form-section">
          <legend>Personal details</legend>
          <div className="form-grid">
            <div className="field"><label htmlFor="itp-dob">Date of birth</label><input id="itp-dob" type="date" max={new Date().toISOString().slice(0, 10)} {...text("date_of_birth")} /></div>
            <div className="field"><label htmlFor="itp-city">City</label><input id="itp-city" maxLength={80} autoComplete="address-level2" {...text("city")} /></div>
            <div className="field" style={{ gridColumn: "1 / -1" }}><label htmlFor="itp-address">Address</label><input id="itp-address" maxLength={300} autoComplete="street-address" {...text("address")} /></div>
            <div className="field"><label htmlFor="itp-qualification">Highest qualification</label><input id="itp-qualification" maxLength={120} placeholder="e.g. B.Tech Computer Science" {...text("qualification")} /></div>
            <div className="field"><label htmlFor="itp-year">Graduation year</label><input id="itp-year" type="number" min={1950} max={YEAR_MAX} step={1} inputMode="numeric" {...text("graduation_year")} /></div>
          </div>
        </fieldset>
        <fieldset className="form-section">
          <legend>Emergency contact</legend>
          <div className="form-grid">
            <div className="field"><label htmlFor="itp-ec-name">Emergency contact name</label><input id="itp-ec-name" maxLength={120} autoComplete="off" {...text("emergency_contact_name")} /></div>
            <div className="field"><label htmlFor="itp-ec-relation">Relation</label><input id="itp-ec-relation" maxLength={60} placeholder="e.g. Father" {...text("emergency_contact_relation")} /></div>
            <div className="field"><label htmlFor="itp-ec-phone">Emergency contact phone</label><input id="itp-ec-phone" type="tel" maxLength={40} autoComplete="off" placeholder="+91 98765 43210" {...text("emergency_contact_phone")} /></div>
          </div>
          <p className="field-help muted" style={{ margin: 0 }}>Shown only to the student, their IT counselor and the IT Admin.</p>
        </fieldset>
        {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} style={{ margin: 0 }}>{message.text}</p>}
        <button className="btn" type="submit" disabled={saving} style={{ justifySelf: "start" }}>{saving ? "Saving…" : "Save details"}</button>
      </form>

      <section aria-labelledby="itp-enrolments" style={{ display: "grid", gap: 12 }}>
        <h4 id="itp-enrolments" style={{ margin: 0 }}>Enrolments</h4>
        {enrollments.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>No enrolments yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table stack compact" aria-label="Enrolments">
              <thead><tr><th scope="col">Programme</th><th scope="col">Batch</th><th scope="col">Status</th><th scope="col">Start</th><th scope="col">End</th><th scope="col">Mode</th><th scope="col">Dates</th></tr></thead>
              <tbody>
                {enrollments.map((e) => (
                  <tr key={e.id}>
                    <td data-label="Programme">{e.program}</td>
                    <td data-label="Batch">{e.batch}</td>
                    {/* itc-031 (DEC-SCOPE-359): the derived stage; the student's own view never says "At risk" (the API's safe subset) */}
                    <td data-label="Status">{e.lifecycle ? <span className={stageTone(e.lifecycle.stage)}>{e.lifecycle.stage_label}</span> : "-"}</td>
                    <td data-label="Start">{formatCalendarDate(e.start_date)}</td>
                    <td data-label="End">{formatCalendarDate(e.end_date)}</td>
                    <td data-label="Mode">{e.delivery_mode}</td>
                    <td data-label="Dates">{e.start_date_override || e.end_date_override || e.delivery_mode_override ? "Set for this student" : "Batch default"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {enrollmentsUrl && enrollments.map((e) => <EnrollmentDates key={e.id} enrollment={e} url={`${enrollmentsUrl}/${encodeURIComponent(e.id)}`} onSaved={saved} />)}
      </section>
    </div>
  );
}

/** One enrolment's override editor (staff). An empty field follows the batch, shown as its placeholder text. */
function EnrollmentDates({ enrollment: e, url, onSaved }: { enrollment: ItEnrollment; url: string; onSaved: (data: ItStudentProfileResponse) => void }) {
  const [start, setStart] = useState(e.start_date_override ?? "");
  const [end, setEnd] = useState(e.end_date_override ?? "");
  const [mode, setMode] = useState(e.delivery_mode_override ?? "");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const inFlight = useRef(false);
  const id = `itp-e-${e.id}`;

  async function send(body: { start_date: string | null; end_date: string | null; delivery_mode: string | null }) {
    if (inFlight.current) return;
    inFlight.current = true;
    setSaving(true);
    setMessage(null);
    const outcome = await sendJson(url, "PATCH", body);
    inFlight.current = false;
    setSaving(false);
    if (!outcome.ok) return setMessage({ text: refusal(outcome.detail, outcome.message), failed: true });
    const data = outcome.data as ItStudentProfileResponse;
    const now = data.enrollments.find((row) => row.id === e.id);
    setStart(now?.start_date_override ?? "");
    setEnd(now?.end_date_override ?? "");
    setMode(now?.delivery_mode_override ?? "");
    setMessage({ text: "Dates saved.", failed: false });
    onSaved(data);
  }

  return (
    <fieldset className="form-section" aria-label={`Dates for ${e.enrollment_code}`}>
      <legend>{e.program} · {e.batch}</legend>
      <p className="field-help muted" style={{ margin: 0 }}>
        Batch: {formatCalendarDate(e.batch_start_date)} – {formatCalendarDate(e.batch_end_date)}, {e.batch_mode}. Leave a field empty to follow the batch.
      </p>
      <div className="form-grid">
        <div className="field"><label htmlFor={`${id}-start`}>Start date</label><input id={`${id}-start`} type="date" value={start} onChange={(ev) => setStart(ev.target.value)} /></div>
        <div className="field"><label htmlFor={`${id}-end`}>End date</label><input id={`${id}-end`} type="date" value={end} min={start || e.batch_start_date} onChange={(ev) => setEnd(ev.target.value)} /></div>
        <div className="field">
          <label htmlFor={`${id}-mode`}>Delivery mode</label>
          <select id={`${id}-mode`} value={mode} onChange={(ev) => setMode(ev.target.value)}>
            <option value="">Batch&apos;s ({e.batch_mode})</option>
            {IT_DELIVERY_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
      </div>
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} style={{ margin: 0 }}>{message.text}</p>}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" className="btn small" disabled={saving} onClick={() => send({ start_date: start || null, end_date: end || null, delivery_mode: mode || null })}>{saving ? "Saving…" : "Save dates"}</button>
        <button type="button" className="btn small secondary" disabled={saving} onClick={() => send({ start_date: null, end_date: null, delivery_mode: null })}>Use batch dates</button>
      </div>
    </fieldset>
  );
}

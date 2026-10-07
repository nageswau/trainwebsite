"use client";

import { type FormEvent, useEffect, useId, useState } from "react";

import { nowIstInput } from "@/lib/bdmAppointments";
import { fieldErrors } from "@/lib/bdmTravel";
import { isRequestBody, sendJson } from "@/lib/apiErrors";
import { appointmentsUrl, bookingBody, clashText, optionsUrl, type AppointmentOptions, type BookingDraft, type LeadAppointment } from "@/lib/leadAppointments";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

const EMPTY: BookingDraft = { appointment_type: "", counselor_id: "", when: "", mode: "Online", meeting_link: "", location: "", purpose: "", remarks: "" };
// Form order, so the first refused field is the one focused (the API's keys: scheduled_at is the "when" input).
const ORDER = ["appointment_type", "counselor_id", "scheduled_at", "mode", "meeting_link", "location", "purpose", "remarks"] as const;
const REQUIRED = { appointment_type: "Choose the appointment type.", counselor_id: "Choose a counselor.", scheduled_at: "Choose the date and time." };

/** tel-016 (EVID-019 §9; AP1, AP4, AP7, AP8): book counselling for a lead. The options (types and counselors of the lead's division) are
 *  read when the form opens; the API checks everything again -- the time, the counselor's clash, one open appointment per lead. */
export default function BookCounsellingForm({ leadId, onBooked, onCancel }: {
  leadId: string; onBooked: (appointment: LeadAppointment) => void; onCancel: () => void;
}) {
  const idp = useId();
  const focus = useFocusAfterRender();
  const [options, setOptions] = useState<AppointmentOptions | "failed" | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [draft, setDraft] = useState<BookingDraft>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useLeaveGuard(JSON.stringify(draft) !== JSON.stringify(EMPTY) && !busy, "Discard this booking?");

  useEffect(() => {
    const controller = new AbortController();
    fetch(optionsUrl(leadId), { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Request failed (${response.status})`);
        setOptions((await response.json()) as AppointmentOptions);
      })
      .catch(() => controller.signal.aborted || setOptions("failed"));
    return () => controller.abort();
  }, [leadId, attempt]);

  const id = (key: string) => `${idp}-${key}`;
  const set = (key: keyof BookingDraft, value: string) => {
    setDraft((d) => ({ ...d, [key]: value }));
    // QA-01: a corrected field drops its own error (the date input reports as the API's `scheduled_at`)
    const field = key === "when" ? "scheduled_at" : key;
    setErrors((e) => (e[field] ? Object.fromEntries(Object.entries(e).filter(([k]) => k !== field)) : e));
  };

  function refuse(found: Record<string, string>, message: string) {
    setErrors(found);
    setFailure(message);
    const first = ORDER.find((key) => found[key]);
    focus(...(first ? [id(first)] : []), id("message"));
  }

  async function book(event: FormEvent) {
    event.preventDefault();
    const local: Record<string, string> = {};
    if (!draft.appointment_type) local.appointment_type = REQUIRED.appointment_type;
    if (!draft.counselor_id) local.counselor_id = REQUIRED.counselor_id;
    if (!draft.when) local.scheduled_at = REQUIRED.scheduled_at;
    if (Object.keys(local).length) return refuse(local, "Check the highlighted fields.");
    setErrors({});
    setFailure(null);
    setBusy(true);
    const outcome = await sendJson(appointmentsUrl(leadId), "POST", bookingBody(draft));
    setBusy(false);
    if (!outcome.ok) {
      const mapped = fieldErrors(outcome.detail);
      if (Object.keys(mapped).length) return refuse(mapped, "Check the highlighted fields.");
      const clash = clashText(outcome.detail);
      return refuse(clash ? { scheduled_at: "The counselor is busy at this time." } : {}, clash ?? outcome.message);
    }
    if (!isRequestBody(outcome.data)) return refuse({}, "Unable to book the appointment.");
    setDraft(EMPTY);
    onBooked(outcome.data as unknown as LeadAppointment);
  }

  if (options === null) return <p className="muted" role="status" style={{ fontSize: 13 }}>Loading the booking form…</p>;
  if (options === "failed") {
    return (
      <p className="form-error" role="alert" style={{ fontSize: 13 }}>
        Unable to load the booking form. <button type="button" className="btn secondary small" onClick={() => { setOptions(null); setAttempt((n) => n + 1); }}>Try again</button>
      </p>
    );
  }

  const invalid = (key: string) => (errors[key] ? { "aria-invalid": true as const, "aria-describedby": `${id(key)}-error` } : {});
  const error = (key: string) => errors[key] && <p id={`${id(key)}-error`} className="form-error" style={{ margin: 0 }}>{errors[key]}</p>;
  const text = (key: "meeting_link" | "location" | "purpose" | "remarks", label: string, max: number, type = "text") => (
    <div className="field">
      <label htmlFor={id(key)}>{label}</label>
      {key === "purpose" || key === "remarks" ? (
        <textarea id={id(key)} rows={2} maxLength={max} value={draft[key]} disabled={busy} onChange={(e) => set(key, e.target.value)} {...invalid(key)} />
      ) : (
        <input id={id(key)} type={type} maxLength={max} value={draft[key]} disabled={busy} onChange={(e) => set(key, e.target.value)} {...invalid(key)} />
      )}
      {error(key)}
    </div>
  );
  const noCounselors = options.counselors.length === 0;
  return (
    <form onSubmit={book} noValidate aria-labelledby={id("heading")} style={{ display: "grid", gap: 8 }}>
      <h4 id={id("heading")} style={{ margin: 0 }}>Book counselling</h4>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>Each appointment lasts {options.duration_minutes} minutes. Times are India time (IST).</p>
      {noCounselors && <p className="form-error" role="alert" style={{ margin: 0 }}>There is no active counselor in this lead&apos;s division yet.</p>}
      <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
        <div className="field">
          <label htmlFor={id("appointment_type")}>Appointment type</label>
          <select id={id("appointment_type")} value={draft.appointment_type} disabled={busy} aria-required onChange={(e) => set("appointment_type", e.target.value)} {...invalid("appointment_type")}>
            <option value="">Choose a type</option>
            {options.types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
          {error("appointment_type")}
        </div>
        <div className="field">
          <label htmlFor={id("counselor_id")}>Counselor</label>
          <select id={id("counselor_id")} value={draft.counselor_id} disabled={busy || noCounselors} aria-required onChange={(e) => set("counselor_id", e.target.value)} {...invalid("counselor_id")}>
            <option value="">Choose a counselor</option>
            {options.counselors.map((c) => <option key={c.id} value={c.id}>{c.full_name}</option>)}
          </select>
          {error("counselor_id")}
        </div>
        <div className="field">
          <label htmlFor={id("scheduled_at")}>Date and time (IST)</label>
          <input id={id("scheduled_at")} type="datetime-local" min={nowIstInput()} value={draft.when} disabled={busy} aria-required
            onChange={(e) => set("when", e.target.value)} {...invalid("scheduled_at")} />
          {error("scheduled_at")}
        </div>
        <div className="field">
          <label htmlFor={id("mode")}>Mode</label>
          <select id={id("mode")} value={draft.mode} disabled={busy} onChange={(e) => set("mode", e.target.value)} {...invalid("mode")}>
            {options.modes.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          {error("mode")}
        </div>
        {text("meeting_link", "Meeting link", 500, "url")}
        {text("location", "Location", 200)}
      </div>
      {text("purpose", "Purpose", 500)}
      {text("remarks", "Remarks", 1000)}
      {failure && <p id={id("message")} tabIndex={-1} className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button type="submit" className="btn small" disabled={busy || noCounselors}>{busy ? "Booking…" : "Book appointment"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

"use client";
import { type ChangeEvent, type FormEvent, useId, useState } from "react";

import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { istInputToIso, isoToIstInput, nowIstInput } from "@/lib/bdmAppointments";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { companyMeetingsUrl, isRecMeeting, MEETING_TYPES, meetingUrl, MODES, PURPOSE_MAX, recruiterOptions, type RecMeeting } from "@/lib/recruiterMeetings";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

export type ContactOption = { id: string; name: string };
type Person = { id: string; full_name: string };
type Values = { type: string; start: string; mode: string; location: string; url: string; purpose: string; contact_id: string; reason: string };

const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));

// rec-028 (spec §4; MT1-MT6): schedule a company meeting, or edit / reschedule a scheduled one. Times are entered and shown in IST. The
// primary contact and the participant contacts come from the company's active contacts (a stored one since deactivated stays listed);
// recruiters are added through the searchable picker. The API decides every rule; this form places its answers on the fields and never
// clears typed text.
export default function RecruiterMeetingForm({ companyId, contacts, meeting, onSaved, onCancel }: {
  companyId: string; contacts: ContactOption[]; meeting?: RecMeeting; onSaved: (meeting: RecMeeting) => void; onCancel: () => void;
}) {
  const id = useId();
  const [start] = useState<Values>({
    type: meeting?.meeting_type ?? "", start: meeting ? isoToIstInput(meeting.starts_at) : "", mode: meeting?.mode ?? "Online",
    location: meeting?.location ?? "", url: meeting?.meeting_url ?? "", purpose: meeting?.purpose ?? "", contact_id: meeting?.contact?.id ?? "", reason: "",
  });
  const startContacts = meeting?.participants.contacts.map((c) => c.id) ?? [];
  const startRecruiters = meeting?.participants.recruiters ?? [];
  const [v, setV] = useState(start);
  const [picked, setPicked] = useState<string[]>(startContacts);
  const [recruiters, setRecruiters] = useState<Person[]>(startRecruiters);
  const [pickerKey, setPickerKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [now] = useState(nowIstInput);
  const recruiterIds = recruiters.map((r) => r.id);
  const dirty = (Object.keys(start) as (keyof Values)[]).some((key) => v[key] !== start[key]) || !sameSet(picked, startContacts)
    || !sameSet(recruiterIds, startRecruiters.map((r) => r.id));
  useLeaveGuard(!busy && dirty, "Discard this meeting?");
  // Stored participants since deactivated stay listed, so editing other fields never drops them.
  const options = [...contacts, ...(meeting?.participants.contacts ?? []).filter((c) => !contacts.some((o) => o.id === c.id))];
  const fid = (key: string) => `${id}-${key}`;
  const set = (key: keyof Values) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setV({ ...v, [key]: e.target.value });
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;
  const toggle = (contactId: string) => setPicked(picked.includes(contactId) ? picked.filter((x) => x !== contactId) : [...picked, contactId]);
  const rescheduled = meeting !== undefined && v.start !== start.start;

  function send(): Promise<SendOutcome> | null {
    const body: Record<string, unknown> = {
      meeting_type: v.type, starts_at: istInputToIso(v.start), mode: v.mode, location: v.location.trim() || null, meeting_url: v.url.trim() || null,
      purpose: v.purpose.trim() || null, contact_id: v.contact_id || null, participant_contact_ids: picked, participant_user_ids: recruiterIds,
    };
    if (!meeting) return sendJson(companyMeetingsUrl(companyId), "POST", body);
    const changes: Record<string, unknown> = {};
    if (v.type !== start.type) changes.meeting_type = body.meeting_type;
    if (rescheduled) Object.assign(changes, { starts_at: body.starts_at, reschedule_reason: v.reason.trim() || null });
    if (v.mode !== start.mode) changes.mode = body.mode;
    if (body.location !== (meeting.location ?? null)) changes.location = body.location;
    if (body.meeting_url !== (meeting.meeting_url ?? null)) changes.meeting_url = body.meeting_url;
    if (body.purpose !== (meeting.purpose ?? null)) changes.purpose = body.purpose;
    if (v.contact_id !== start.contact_id) changes.contact_id = body.contact_id;
    if (!sameSet(picked, startContacts)) changes.participant_contact_ids = picked;
    if (!sameSet(recruiterIds, startRecruiters.map((r) => r.id))) changes.participant_user_ids = recruiterIds;
    return Object.keys(changes).length ? sendJson(meetingUrl(meeting.id), "PATCH", changes) : null;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const missing: Record<string, string> = {};
    if (!v.type) missing.meeting_type = "Choose a meeting type";
    if (!v.start) missing.starts_at = "Choose a date and time";
    if (Object.keys(missing).length) return setErrors(missing);
    const request = send();
    if (!request) return onCancel();
    setBusy(true);
    setErrors({});
    setFailure(null);
    setSessionEnded(false);
    const result = await request;
    setBusy(false);
    if (result.ok) return isRecMeeting(result.data) ? onSaved(result.data) : setFailure(SAVE_FAILED);
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    const kind = writeFailure(result.status);
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message); // a refusal (archived, changed meanwhile) in the server's words
  }

  return (
    <form aria-label={meeting ? "Edit meeting" : "Schedule meeting"} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
        <div className="field">
          <label htmlFor={fid("meeting_type")}>Meeting type (required)</label>
          <select id={fid("meeting_type")} autoFocus required aria-required="true" value={v.type} onChange={set("type")} {...invalid("meeting_type")}>
            <option value="">Select a type</option>
            {MEETING_TYPES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
          {error("meeting_type")}
        </div>
        <div className="field">
          <label htmlFor={fid("starts_at")}>Date and time (IST, required)</label>
          <input id={fid("starts_at")} type="datetime-local" required aria-required="true" min={now} value={v.start} onChange={set("start")} {...invalid("starts_at")} />
          {error("starts_at")}
        </div>
        <div className="field">
          <label htmlFor={fid("mode")}>Mode (required)</label>
          <select id={fid("mode")} required aria-required="true" value={v.mode} onChange={set("mode")} {...invalid("mode")}>
            {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          {error("mode")}
        </div>
        <div className="field">
          <label htmlFor={fid("location")}>Location</label>
          <input id={fid("location")} maxLength={200} value={v.location} onChange={set("location")} {...invalid("location")} />
          {error("location")}
        </div>
        <div className="field">
          <label htmlFor={fid("meeting_url")}>Meeting link</label>
          <input id={fid("meeting_url")} type="url" inputMode="url" maxLength={500} placeholder="https://" value={v.url} onChange={set("url")} {...invalid("meeting_url")} />
          {error("meeting_url")}
        </div>
        <div className="field">
          <label htmlFor={fid("contact_id")}>Contact</label>
          <select id={fid("contact_id")} value={v.contact_id} onChange={set("contact_id")} {...invalid("contact_id")}>
            <option value="">No primary contact</option>
            {options.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          {error("contact_id")}
        </div>
      </div>
      {rescheduled && (
        <div className="field">
          <label htmlFor={fid("reschedule_reason")}>Reason for rescheduling</label>
          <input id={fid("reschedule_reason")} maxLength={500} value={v.reason} onChange={set("reason")} {...invalid("reschedule_reason")} />
          {error("reschedule_reason")}
        </div>
      )}
      <div className="field">
        <label htmlFor={fid("purpose")}>Purpose</label>
        <textarea id={fid("purpose")} rows={2} maxLength={PURPOSE_MAX} value={v.purpose} onChange={set("purpose")} aria-invalid={errors.purpose ? true : undefined}
          aria-describedby={errors.purpose ? `${fid("purpose")}-count ${fid("purpose")}-error` : `${fid("purpose")}-count`} />
        <p id={`${fid("purpose")}-count`} className="muted" style={{ margin: 0 }}>{v.purpose.length}/{PURPOSE_MAX}</p>
        {error("purpose")}
      </div>
      <fieldset className="field" aria-describedby={errors.participant_contact_ids ? `${fid("participant_contact_ids")}-error` : undefined} style={{ border: 0, padding: 0, margin: 0 }}>
        <legend>Participants: contacts</legend>
        {options.length === 0 ? (
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>This company has no active contacts yet.</p>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 16px" }}>
            {options.map((c) => (
              <label key={c.id} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                <input type="checkbox" checked={picked.includes(c.id) || v.contact_id === c.id} disabled={v.contact_id === c.id} onChange={() => toggle(c.id)} />
                {c.name}{v.contact_id === c.id && <span className="muted"> (primary)</span>}
              </label>
            ))}
          </div>
        )}
        {error("participant_contact_ids")}
      </fieldset>
      <div className="field">
        <SearchableSelect key={pickerKey} label="Add a recruiter" noun="recruiter" search={recruiterOptions}
          onChange={(option) => {
            if (option && !recruiterIds.includes(option.id)) setRecruiters([...recruiters, { id: option.id, full_name: option.label }]);
            if (option) setPickerKey((n) => n + 1);
          }} />
        {recruiters.length > 0 && (
          <ul aria-label="Recruiter participants" style={{ display: "flex", flexWrap: "wrap", gap: 6, padding: 0, margin: "4px 0 0" }}>
            {recruiters.map((r) => (
              <li key={r.id} className="badge" style={{ listStyle: "none", display: "inline-flex", gap: 4, alignItems: "center" }}>
                {r.full_name}
                <button type="button" className="btn secondary small" aria-label={`Remove ${r.full_name}`} onClick={() => setRecruiters(recruiters.filter((x) => x.id !== r.id))}>×</button>
              </li>
            ))}
          </ul>
        )}
        {error("participant_user_ids")}
      </div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {sessionEnded && (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref={RECRUITER_SIGN_IN} />
        </div>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : meeting ? "Save changes" : "Schedule meeting"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

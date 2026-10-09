"use client";
import { type ChangeEvent, type FormEvent, useId, useRef, useState } from "react";

import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { istInputToIso, nowIstInput } from "@/lib/bdmAppointments";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { interviewOf, INTERVIEWS_URL, interviewUrl, type Notices, type RecInterview, ROUNDS } from "@/lib/recruiterInterviews";
import { MODES } from "@/lib/recruiterMeetings";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

export type ContactOption = { id: string; name: string };
type Values = { round: string; start: string; mode: string; url: string; interviewer: string; location: string; contact_id: string };

// rec-020 (spec §4; IV5, IV7): schedule an interview for one application, or edit the details of one (the time changes only through
// Reschedule). The time is entered in IST. The contact comes from the requirement company's active contacts (a stored one since
// deactivated stays listed). The API decides every rule; its 422s are placed on their fields and typed text is never cleared.
export default function RecruiterInterviewForm({ applicationId, interview, contacts, onSaved, onCancel }: {
  applicationId?: string; interview?: RecInterview; contacts: ContactOption[];
  onSaved: (interview: RecInterview, notices?: Notices) => void; onCancel: () => void;
}) {
  const id = useId();
  const [start] = useState<Values>({
    round: interview?.round ?? "", start: "", mode: interview?.mode ?? "Online", url: interview?.meeting_url ?? "",
    interviewer: interview?.interviewer ?? "", location: interview?.location ?? "", contact_id: interview?.contact?.id ?? "",
  });
  const [v, setV] = useState(start);
  const [notify, setNotify] = useState(true);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // QA-01: a fast double click runs submit twice before `busy` re-renders the button disabled
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [now] = useState(nowIstInput);
  const dirty = (Object.keys(start) as (keyof Values)[]).some((key) => v[key] !== start[key]);
  useLeaveGuard(!busy && dirty, "Discard this interview?");
  const options = [...contacts, ...(interview?.contact && !contacts.some((c) => c.id === interview.contact?.id) ? [interview.contact] : [])];
  const fid = (key: string) => `${id}-${key}`;
  const set = (key: keyof Values) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setV({ ...v, [key]: e.target.value });
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;

  function send(): Promise<SendOutcome> | null {
    const details = {
      round: v.round, mode: v.mode, meeting_url: v.url.trim() || null, interviewer: v.interviewer.trim() || null,
      location: v.location.trim() || null, contact_id: v.contact_id || null,
    };
    if (!interview) return sendJson(INTERVIEWS_URL, "POST", { application_id: applicationId, scheduled_at: istInputToIso(v.start), notify, ...details });
    const stored: Record<string, unknown> = {
      round: interview.round, mode: interview.mode, meeting_url: interview.meeting_url, interviewer: interview.interviewer,
      location: interview.location, contact_id: interview.contact?.id ?? null,
    };
    const changes = Object.fromEntries(Object.entries(details).filter(([key, value]) => value !== stored[key]));
    return Object.keys(changes).length ? sendJson(interviewUrl(interview.id), "PATCH", changes) : null;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const missing: Record<string, string> = {};
    if (!v.round) missing.round = "Choose a round";
    if (!interview && !v.start) missing.scheduled_at = "Choose a date and time";
    if (Object.keys(missing).length) return setErrors(missing);
    if (inFlight.current) return;
    const request = send();
    if (!request) return onCancel();
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setFailure(null);
    setSessionEnded(false);
    const result = await request;
    inFlight.current = false;
    setBusy(false);
    if (result.ok) {
      const saved = interviewOf(result.data);
      return saved ? onSaved(saved, (result.data as { notifications?: Notices }).notifications) : setFailure(SAVE_FAILED);
    }
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    const kind = writeFailure(result.status);
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message); // the clash, a finished application, a decided interview -- in the server's words
  }

  return (
    <form aria-label={interview ? `Edit interview ${interview.code}` : "Schedule interview"} className="action-card" noValidate onSubmit={submit}
      onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(13rem, 1fr))" }}>
        <div className="field">
          <label htmlFor={fid("round")}>Round (required)</label>
          <select id={fid("round")} autoFocus required aria-required="true" value={v.round} onChange={set("round")} {...invalid("round")}>
            <option value="">Select a round</option>
            {ROUNDS.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select>
          {error("round")}
        </div>
        {!interview && (
          <div className="field">
            <label htmlFor={fid("scheduled_at")}>Date and time (IST, required)</label>
            <input id={fid("scheduled_at")} type="datetime-local" required aria-required="true" min={now} value={v.start} onChange={set("start")} {...invalid("scheduled_at")} />
            {error("scheduled_at")}
          </div>
        )}
        <div className="field">
          <label htmlFor={fid("mode")}>Mode (required)</label>
          <select id={fid("mode")} required aria-required="true" value={v.mode} onChange={set("mode")} {...invalid("mode")}>
            {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          {error("mode")}
        </div>
        <div className="field">
          <label htmlFor={fid("meeting_url")}>Meeting link</label>
          <input id={fid("meeting_url")} type="url" inputMode="url" maxLength={500} placeholder="https://" value={v.url} onChange={set("url")} {...invalid("meeting_url")} />
          {error("meeting_url")}
        </div>
        <div className="field">
          <label htmlFor={fid("interviewer")}>Interviewer</label>
          <input id={fid("interviewer")} maxLength={160} value={v.interviewer} onChange={set("interviewer")} {...invalid("interviewer")} />
          {error("interviewer")}
        </div>
        <div className="field">
          <label htmlFor={fid("location")}>Location</label>
          <input id={fid("location")} maxLength={200} value={v.location} onChange={set("location")} {...invalid("location")} />
          {error("location")}
        </div>
        <div className="field">
          <label htmlFor={fid("contact_id")}>Company contact</label>
          <select id={fid("contact_id")} value={v.contact_id} onChange={set("contact_id")} {...invalid("contact_id")}>
            <option value="">No contact</option>
            {options.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          {error("contact_id")}
        </div>
      </div>
      {!interview && (
        <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
          Notify the candidate{v.contact_id ? " and the contact" : ""}
        </label>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {sessionEnded && (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref={RECRUITER_SIGN_IN} />
        </div>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : interview ? "Save changes" : "Schedule interview"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

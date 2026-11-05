"use client";
import { type ChangeEvent, type FormEvent, useId, useRef, useState } from "react";

import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import StaleRecordNotice from "@/components/StaleRecordNotice";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { istInputToIso, nowIstInput } from "@/lib/bdmAppointments";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import {
  DOCUMENTS_MAX,
  DURATIONS,
  durationOf,
  endsAt,
  INSTRUCTIONS_MAX,
  interviewOf,
  INTERVIEWS_URL,
  interviewUrl,
  IST_ZONE,
  type Notices,
  PHONE_MAX,
  PLATFORMS,
  type RecInterview,
  ROUNDS,
  zoneOptions,
} from "@/lib/recruiterInterviews";
import { MODES } from "@/lib/recruiterMeetings";
import { useStaleGuard } from "@/lib/staleGuard";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

export type ContactOption = { id: string; name: string };
type Values = {
  round: string; start: string; mode: string; url: string; interviewer: string; location: string; contact_id: string;
  // hrc-028 (DEC-SCOPE-399 I1)
  round_number: string; duration: string; time_zone: string; platform: string; phone: string; instructions: string; documents: string;
};
const LABELS: Record<string, string> = { round: "Round", mode: "Mode", url: "Meeting link", meeting_url: "Meeting link", interviewer: "Interviewer", location: "Location",
  contact_id: "Company contact", status: "Status", reschedule: "Date and time", feedback: "Feedback", round_number: "Round number", ends_at: "Duration",
  time_zone: "Candidate's time zone", platform: "Platform", phone_details: "Phone details", instructions: "Instructions", documents_required: "Documents to bring" };
const ROUND_NUMBER = /^(?:[1-9]|1\d|20)$/;
/** The details as the API takes them (blank = null); the end is the start plus the chosen duration. */
const details = (v: Values, startIso: string) => ({
  round: v.round, mode: v.mode, meeting_url: v.url.trim() || null, interviewer: v.interviewer.trim() || null, location: v.location.trim() || null, contact_id: v.contact_id || null,
  round_number: v.round_number ? Number(v.round_number) : null, ends_at: endsAt(startIso, v.duration), time_zone: v.time_zone, platform: v.platform || null,
  phone_details: v.phone.trim() || null, instructions: v.instructions.trim() || null, documents_required: v.documents.trim() || null,
});

// rec-020 (spec §4; IV5, IV7): schedule an interview for one application, or edit the details of one (the time changes only through
// Reschedule). The time is entered in IST. The contact comes from the requirement company's active contacts (a stored one since
// deactivated stays listed). The API decides every rule; its 422s are placed on their fields and typed text is never cleared.
export default function RecruiterInterviewForm({ applicationId, interview, draftRound, contacts, onSaved, onLatest, onCancel }: {
  applicationId?: string; interview?: RecInterview; draftRound?: string; contacts: ContactOption[];
  onSaved: (interview: RecInterview, notices?: Notices) => void; onCancel: () => void;
  /** hrc-003: the latest interview after a stale save was reloaded or reviewed, for the page behind the form. */
  onLatest?: (interview: RecInterview) => void;
}) {
  const id = useId();
  // hrc-003: an edit keeps the details and `updated_at` it opened with; a save refused as stale re-bases them (Reload / Review).
  const guard = useStaleGuard<RecInterview, Values>(interview, (i) => ({
    round: i?.round ?? draftRound ?? "", start: "", mode: i?.mode ?? "Online", url: i?.meeting_url ?? "",
    interviewer: i?.interviewer ?? "", location: i?.location ?? "", contact_id: i?.contact?.id ?? "",
    round_number: i?.round_number ? String(i.round_number) : "", duration: i ? durationOf(i) : "", time_zone: i?.time_zone ?? IST_ZONE,
    platform: i?.platform ?? "", phone: i?.phone_details ?? "", instructions: i?.instructions ?? "", documents: i?.documents_required ?? "",
  }), (i) => i?.updated_at ?? null, onLatest);
  const { values: v, setValues: setV, opened: start } = guard;
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
  const set = (key: keyof Values) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setV({ ...v, [key]: e.target.value });
  const durations = v.duration && !DURATIONS.includes(v.duration) ? [...DURATIONS, v.duration] : DURATIONS; // a stored odd length stays selectable
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;

  function send(): Promise<SendOutcome> | null {
    if (!interview) {
      const at = istInputToIso(v.start);
      return sendJson(INTERVIEWS_URL, "POST", { application_id: applicationId, scheduled_at: at, notify, ...details(v, at) });
    }
    const opened: Record<string, unknown> = details(start, interview.scheduled_at);
    const changes = Object.fromEntries(Object.entries(details(v, interview.scheduled_at)).filter(([key, value]) => value !== opened[key]));
    if (!Object.keys(changes).length) return null;
    return sendJson(interviewUrl(interview.id), "PATCH", { ...changes, expected_updated_at: guard.token, ...(notify ? {} : { notify: false }) }); // hrc-028 (I5)
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const missing: Record<string, string> = {};
    if (!v.round) missing.round = "Choose a round";
    if (!interview && !v.start) missing.scheduled_at = "Choose a date and time";
    if (v.round_number && !ROUND_NUMBER.test(v.round_number)) missing.round_number = "Enter a round number from 1 to 20";
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
    if (guard.caught(result)) return;
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
        <div className="field">
          <label htmlFor={fid("round_number")}>Round number</label>
          <input id={fid("round_number")} type="number" inputMode="numeric" min={1} max={20} step={1} value={v.round_number} onChange={set("round_number")}
            {...invalid("round_number")} />
          {error("round_number")}
        </div>
        <div className="field">
          <label htmlFor={fid("ends_at")}>Duration</label>
          <select id={fid("ends_at")} value={v.duration} onChange={set("duration")} {...invalid("ends_at")}>
            <option value="">Not set</option>
            {durations.map((m) => <option key={m} value={m}>{Number(m) < 60 ? `${m} min` : `${Number(m) / 60} h`}</option>)}
          </select>
          {error("ends_at")}
        </div>
        <div className="field">
          <label htmlFor={fid("time_zone")}>Candidate&apos;s time zone</label>
          <select id={fid("time_zone")} value={v.time_zone} onChange={set("time_zone")} {...invalid("time_zone")}>
            {zoneOptions(interview?.time_zone).map((z) => <option key={z} value={z}>{z === IST_ZONE ? `${z} (IST)` : z}</option>)}
          </select>
          {error("time_zone")}
        </div>
        <div className="field">
          <label htmlFor={fid("platform")}>Platform</label>
          <select id={fid("platform")} value={v.platform} onChange={set("platform")} {...invalid("platform")}>
            <option value="">Not set</option>
            {PLATFORMS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select>
          {error("platform")}
        </div>
        <div className="field">
          <label htmlFor={fid("phone_details")}>Phone details</label>
          <input id={fid("phone_details")} maxLength={PHONE_MAX} value={v.phone} onChange={set("phone")} {...invalid("phone_details")} />
          {error("phone_details")}
        </div>
      </div>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(min(16rem, 100%), 1fr))" }}>
        <div className="field">
          <label htmlFor={fid("instructions")}>Instructions</label>
          <textarea id={fid("instructions")} rows={2} maxLength={INSTRUCTIONS_MAX} value={v.instructions} onChange={set("instructions")} {...invalid("instructions")} />
          {error("instructions")}
        </div>
        <div className="field">
          <label htmlFor={fid("documents_required")}>Documents to bring</label>
          <textarea id={fid("documents_required")} rows={2} maxLength={DOCUMENTS_MAX} value={v.documents} onChange={set("documents")} {...invalid("documents_required")} />
          {error("documents_required")}
        </div>
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>Times are entered in IST; the candidate reads them in their own time zone.</p>
      <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
        <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
        Notify the candidate{v.contact_id ? " and the contact" : ""}{interview ? " of the changes they can see" : ""}
      </label>
      <StaleRecordNotice
        guard={guard}
        labelOf={(key) => LABELS[key] ?? key.replace(/_/g, " ")}
        display={(key, value) => (key === "round" ? (ROUNDS.find((r) => r.key === value)?.label ?? value) : key === "contact_id" ? (options.find((c) => c.id === value)?.name ?? value) : value)}
        onReload={guard.reload}
        onReview={guard.reviewMine}
      />
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

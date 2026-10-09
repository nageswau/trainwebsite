"use client";
import Link from "next/link";
import { type FormEvent, type ReactNode, useId, useState } from "react";

import RecruiterInterviewForm, { type ContactOption } from "@/components/RecruiterInterviewForm";
import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { istInputToIso, nowIstInput } from "@/lib/bdmAppointments";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { RECRUITER_SIGN_IN, safeLink } from "@/lib/recruiterCompanies";
import { interviewOf, interviewUrl, type InterviewEvent, NOTE_MAX, type Notices, noticeText, type RecInterview, STATUS_LABELS } from "@/lib/recruiterInterviews";
import { REQUIREMENTS_PATH } from "@/lib/recruiterRequirements";

const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;
type Failure = { kind: "session" | "error"; message: string };
type Saved = (interview: RecInterview, notices?: Notices) => void;

function failureOf(result: Extract<SendOutcome, { ok: false }>): Failure {
  const kind = writeFailure(result.status);
  if (kind === "session") return { kind, message: SESSION_ENDED };
  return { kind: "error", message: kind === "retry" ? SAVE_FAILED : result.message };
}

/** One small form's submit: the API's 422s go on their fields; a refusal (409 clash, 422 "not yet") stays on the form in its words. */
function useSubmit(onSaved: Saved) {
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<Failure | null>(null);
  async function run(request: Promise<SendOutcome>) {
    setBusy(true);
    setErrors({});
    setFailure(null);
    const result = await request;
    setBusy(false);
    if (result.ok) {
      const saved = interviewOf(result.data);
      return saved ? onSaved(saved, (result.data as { notifications?: Notices }).notifications) : setFailure({ kind: "error", message: SAVE_FAILED });
    }
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    setFailure(failureOf(result));
  }
  return { busy, errors, setErrors, failure, run };
}

function Problem({ failure }: { failure: Failure | null }) {
  if (!failure) return null;
  return (
    <div role="alert">
      <p className="form-error">{failure.message}</p>
      {failure.kind === "session" && <ReturnToLoginLink loginHref={RECRUITER_SIGN_IN} />}
    </div>
  );
}

function Field({ id, label, error, children }: { id: string; label: string; error?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {error && <p id={`${id}-error`} className="form-error">{error}</p>}
    </div>
  );
}

/** IV3: one of the moves the API allows now, with an optional note. */
function StatusForm({ interview, onSaved, onCancel }: { interview: RecInterview; onSaved: Saved; onCancel: () => void }) {
  const id = useId();
  const [status, setStatus] = useState("");
  const [note, setNote] = useState("");
  const { busy, errors, setErrors, failure, run } = useSubmit(onSaved);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!status) return setErrors({ status: "Choose a status" });
    void run(sendJson(interviewUrl(interview.id, "status"), "POST", { status, ...(note.trim() ? { note: note.trim() } : {}) }));
  }
  return (
    <form aria-label={`Change status of ${interview.code}`} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <Field id={`${id}-status`} label="New status (required)" error={errors.status}>
        <select id={`${id}-status`} autoFocus required aria-required="true" value={status} onChange={(e) => setStatus(e.target.value)}
          aria-invalid={errors.status ? true : undefined} aria-describedby={errors.status ? `${id}-status-error` : undefined}>
          <option value="">Choose a status</option>
          {interview.allowed_statuses.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
      </Field>
      <Field id={`${id}-note`} label="Note (optional)" error={errors.note}>
        <textarea id={`${id}-note`} rows={2} maxLength={NOTE_MAX} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <Problem failure={failure} />
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save status"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** IV4 / AC1: a new time (IST), an optional reason and the notice choice; the old and new times are kept in the history. */
function RescheduleForm({ interview, onSaved, onCancel }: { interview: RecInterview; onSaved: Saved; onCancel: () => void }) {
  const id = useId();
  const [start, setStart] = useState("");
  const [reason, setReason] = useState("");
  const [notify, setNotify] = useState(true);
  const [now] = useState(nowIstInput);
  const { busy, errors, setErrors, failure, run } = useSubmit(onSaved);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!start) return setErrors({ scheduled_at: "Choose the new date and time" });
    void run(sendJson(interviewUrl(interview.id, "reschedule"), "POST", { scheduled_at: istInputToIso(start), reason: reason.trim() || null, notify }));
  }
  return (
    <form aria-label={`Reschedule ${interview.code}`} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(13rem, 1fr))" }}>
        <Field id={`${id}-at`} label="New date and time (IST, required)" error={errors.scheduled_at}>
          <input id={`${id}-at`} type="datetime-local" autoFocus required aria-required="true" min={now} value={start} onChange={(e) => setStart(e.target.value)}
            aria-invalid={errors.scheduled_at ? true : undefined} aria-describedby={errors.scheduled_at ? `${id}-at-error` : undefined} />
        </Field>
        <Field id={`${id}-reason`} label="Reason" error={errors.reason}>
          <input id={`${id}-reason`} maxLength={NOTE_MAX} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
      </div>
      <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
        <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
        Notify the candidate{interview.contact ? " and the contact" : ""}
      </label>
      <Problem failure={failure} />
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Reschedule"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function historyText(h: InterviewEvent): string {
  const by = h.actor ? ` by ${h.actor.full_name}` : "";
  const note = h.note ? ` — ${h.note}` : "";
  const at = formatSchoolDateTime(h.created_at, true);
  if (h.event === "scheduled") return `Scheduled ${at}${by}`;
  if (h.event === "rescheduled") {
    const from = h.old_scheduled_at ? formatSchoolDateTime(h.old_scheduled_at, true) : "?";
    const to = h.new_scheduled_at ? formatSchoolDateTime(h.new_scheduled_at, true) : "?";
    return `Rescheduled from ${from} to ${to}${by}${note}`;
  }
  const name = (key: string | null) => (key ? STATUS_LABELS[key] ?? key : "?");
  return `${name(h.from_status)} → ${name(h.to_status)} ${at}${by}${note}`;
}

/** rec-020 (spec §4): one interview with its actions -- Change status, Reschedule and Edit -- offered only when the API allows them.
 *  `card` is the list form (the candidate and requirement first, linked); without it the item sits on its application. */
export default function RecruiterInterviewItem({ interview: i, card = false, contacts = [], onChanged }: {
  interview: RecInterview; card?: boolean; contacts?: ContactOption[]; onChanged: (interview: RecInterview, notice: string) => void;
}) {
  const [mode, setMode] = useState<"view" | "status" | "reschedule" | "edit">("view");
  const id = useId();
  const link = safeLink(i.meeting_url);
  const done = (text: string) => (next: RecInterview, notices?: Notices) => {
    setMode("view");
    onChanged(next, [text, noticeText(notices)].filter(Boolean).join(" "));
  };
  const facts = [
    card && ["Requirement", `${i.requirement.title} · ${i.company.name}`],
    ["When", formatSchoolDateTime(i.scheduled_at, true)],
    ["Mode", i.mode],
    i.interviewer && ["Interviewer", i.interviewer],
    i.location && ["Location", i.location],
    i.contact && ["Contact", i.contact.name],
  ].filter(Boolean) as [string, string][];
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-title`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong id={`${id}-title`}>
          {card ? (
            <Link href={`${REQUIREMENTS_PATH}/${encodeURIComponent(i.requirement.id)}`} style={LINK_STYLE}>{i.candidate.name}</Link>
          ) : (
            i.round_label ?? "Interview"
          )}
        </strong>
        {card && i.round_label && <span>{i.round_label}</span>}
        <span className="muted" style={{ fontSize: 13 }}>{i.code}</span>
        <span className="badge">{i.status_label}</span>
      </div>
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))", gap: "4px 16px", margin: 0 }}>
        {facts.map(([term, value]) => (
          <div key={term}>
            <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
            <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
          </div>
        ))}
      </dl>
      {link && (
        <p style={{ margin: 0, overflowWrap: "anywhere" }}>
          <a href={link} target="_blank" rel="noopener noreferrer">Meeting link<span className="visually-hidden"> (opens in a new tab)</span></a>
        </p>
      )}
      {i.history.length > 0 && (
        <details>
          <summary style={{ cursor: "pointer", fontSize: 13 }}>History ({i.history.length})<span className="visually-hidden"> of {i.code}</span></summary>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 13 }}>
            {i.history.map((h, n) => <li key={`${h.created_at}-${n}`} style={TEXT}>{historyText(h)}</li>)}
          </ul>
        </details>
      )}
      {mode === "status" && <StatusForm interview={i} onCancel={() => setMode("view")} onSaved={done("Status saved.")} />}
      {mode === "reschedule" && <RescheduleForm interview={i} onCancel={() => setMode("view")} onSaved={done("Interview rescheduled.")} />}
      {mode === "edit" && <RecruiterInterviewForm interview={i} contacts={contacts} onCancel={() => setMode("view")} onSaved={done("Interview updated.")} />}
      {mode === "view" && (i.allowed_statuses.length > 0 || i.can_reschedule || i.can_edit) && (
        <div className="actions" style={{ flexWrap: "wrap" }}>
          {i.allowed_statuses.length > 0 && (
            <button type="button" className="btn small" onClick={() => setMode("status")}>Change status<span className="visually-hidden"> of {i.code}</span></button>
          )}
          {i.can_reschedule && (
            <button type="button" className="btn secondary small" onClick={() => setMode("reschedule")}>Reschedule<span className="visually-hidden"> {i.code}</span></button>
          )}
          {i.can_edit && <button type="button" className="btn secondary small" onClick={() => setMode("edit")}>Edit<span className="visually-hidden"> {i.code}</span></button>}
        </div>
      )}
    </li>
  );
}

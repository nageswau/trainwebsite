"use client";
import Link from "next/link";
import { type FormEvent, type ReactNode, useId, useRef, useState } from "react";

import RecruiterInterviewForm, { type ContactOption } from "@/components/RecruiterInterviewForm";
import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { istInputToIso, nowIstInput } from "@/lib/bdmAppointments";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { RECRUITER_SIGN_IN, safeLink } from "@/lib/recruiterCompanies";
import {
  DECISIONS,
  FEEDBACK_TEXT_MAX,
  type FeedbackFields,
  type InterviewEvent,
  type InterviewFeedback,
  interviewOf,
  interviewUrl,
  NOTE_MAX,
  type Notices,
  noticeText,
  type RecInterview,
  type Round,
  ROUNDS,
  STATUS_LABELS,
} from "@/lib/recruiterInterviews";
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
  const inFlight = useRef(false); // QA-01: a fast double click runs submit twice before `busy` re-renders the button disabled
  async function run(send: () => Promise<SendOutcome>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setFailure(null);
    const result = await send();
    inFlight.current = false;
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
    void run(() => sendJson(interviewUrl(interview.id, "status"), "POST", { status, ...(note.trim() ? { note: note.trim() } : {}) }));
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
    void run(() => sendJson(interviewUrl(interview.id, "reschedule"), "POST", { scheduled_at: istInputToIso(start), reason: reason.trim() || null, notify }));
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

const RATINGS = ["1", "2", "3", "4", "5"];
const TEXTS = [["strengths", "Strengths"], ["weaknesses", "Weaknesses"], ["recruiter_comments", "Recruiter comments"], ["company_feedback", "Company feedback"]] as const;
const RATING_FIELDS = [["technical_rating", "Technical"], ["communication_rating", "Communication"]] as const;
// The form's own shape: every value is a string until sent ("" = not given).
type FeedbackDraft = { [K in keyof FeedbackFields]: string };

function feedbackDraft(f: InterviewFeedback | null): FeedbackDraft {
  const str = (v: number | string | null | undefined) => (v === null || v === undefined ? "" : String(v));
  return {
    technical_rating: str(f?.technical_rating), communication_rating: str(f?.communication_rating), overall_rating: str(f?.overall_rating),
    strengths: str(f?.strengths), weaknesses: str(f?.weaknesses), recruiter_comments: str(f?.recruiter_comments),
    company_feedback: str(f?.company_feedback), next_round: str(f?.next_round), final_decision: str(f?.final_decision),
  };
}

function feedbackBody(d: FeedbackDraft): FeedbackFields {
  const num = (v: string) => (v === "" ? null : Number(v));
  const text = (v: string) => v.trim() || null;
  return {
    technical_rating: num(d.technical_rating), communication_rating: num(d.communication_rating), overall_rating: Number(d.overall_rating),
    strengths: text(d.strengths), weaknesses: text(d.weaknesses), recruiter_comments: text(d.recruiter_comments), company_feedback: text(d.company_feedback),
    next_round: (d.next_round || null) as Round | null, final_decision: (d.final_decision || null) as FeedbackFields["final_decision"],
  };
}

/** rec-021 (FB1-FB4): the §15 feedback -- the whole form replaces the saved one; a decision moves the interview (the API decides). */
function FeedbackForm({ interview, onSaved, onCancel }: { interview: RecInterview; onSaved: Saved; onCancel: () => void }) {
  const id = useId();
  const [d, setD] = useState(() => feedbackDraft(interview.feedback));
  const { busy, errors, setErrors, failure, run } = useSubmit(onSaved);
  const set = (key: keyof FeedbackDraft) => (e: { target: { value: string } }) => setD((prev) => ({ ...prev, [key]: e.target.value }));
  const rejected = d.final_decision === "rejected";
  const aria = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${id}-${key}-error` : undefined });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!d.overall_rating) return setErrors({ overall_rating: "Choose an overall rating" });
    void run(() => sendJson(interviewUrl(interview.id, "feedback"), "PUT", feedbackBody(d)));
  }
  function rating(key: "technical_rating" | "communication_rating" | "overall_rating", label: string, required = false) {
    return (
      <Field id={`${id}-${key}`} label={required ? `${label} (required)` : label} error={errors[key]}>
        <select id={`${id}-${key}`} value={d[key]} onChange={set(key)} {...(required ? { required: true, "aria-required": true } : {})} {...aria(key)}>
          <option value="">{required ? "Choose a rating" : "Not rated"}</option>
          {RATINGS.map((r) => <option key={r} value={r}>{r} / 5</option>)}
        </select>
      </Field>
    );
  }
  return (
    <form aria-label={`Feedback for ${interview.code}`} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(min(11rem, 100%), 1fr))" }}>
        {rating("technical_rating", "Technical rating")}
        {rating("communication_rating", "Communication rating")}
        {rating("overall_rating", "Overall rating", true)}
      </div>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(min(16rem, 100%), 1fr))" }}>
        {TEXTS.map(([key, label]) => (
          <Field key={key} id={`${id}-${key}`} label={label} error={errors[key]}>
            <textarea id={`${id}-${key}`} rows={2} maxLength={FEEDBACK_TEXT_MAX} value={d[key]} onChange={set(key)} {...aria(key)} />
          </Field>
        ))}
      </div>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(min(13rem, 100%), 1fr))" }}>
        <Field id={`${id}-final_decision`} label="Final decision" error={errors.final_decision}>
          <select id={`${id}-final_decision`} value={d.final_decision} {...aria("final_decision")}
            onChange={(e) => setD((prev) => ({ ...prev, final_decision: e.target.value, next_round: e.target.value === "rejected" ? "" : prev.next_round }))}>
            <option value="">No decision yet</option>
            {DECISIONS.map((k) => <option key={k} value={k}>{STATUS_LABELS[k]}</option>)}
          </select>
        </Field>
        <Field id={`${id}-next_round`} label="Next round" error={errors.next_round}>
          <select id={`${id}-next_round`} value={d.next_round} onChange={set("next_round")} disabled={rejected} {...aria("next_round")}>
            <option value="">No next round</option>
            {ROUNDS.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select>
        </Field>
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>A decision also sets the interview&apos;s status.</p>
      <Problem failure={failure} />
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save feedback"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** The saved feedback, for every reader of the interview. */
function FeedbackSummary({ code, feedback: f }: { code: string; feedback: InterviewFeedback }) {
  const score = (v: number | null) => (v === null ? "Not rated" : `${v} / 5`);
  const rows: [string, string][] = [
    ["Overall", score(f.overall_rating)],
    ...RATING_FIELDS.map(([key, label]): [string, string] => [label, score(f[key])]),
    ...TEXTS.filter(([key]) => f[key]).map(([key, label]): [string, string] => [label, f[key] as string]),
    ["Next round", f.next_round_label ?? "None"],
    ["Final decision", f.final_decision_label ?? "Not decided"],
  ];
  return (
    <div style={{ display: "grid", gap: 2 }}>
      <strong style={{ fontSize: 13 }}>Feedback</strong>
      <ul aria-label={`Feedback of ${code}`} style={{ margin: 0, paddingLeft: 18, fontSize: 13, display: "grid", gap: 2 }}>
        {rows.map(([name, value]) => <li key={name}><span className="muted">{name}:</span> <span style={TEXT}>{value}</span></li>)}
      </ul>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>Recorded by {f.recorded_by.full_name}, {formatSchoolDateTime(f.updated_at, true)}</p>
    </div>
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
  interview: RecInterview; card?: boolean; contacts?: ContactOption[]; onChanged: (interview: RecInterview, notice: string, nextRound?: Round) => void;
}) {
  const [mode, setMode] = useState<"view" | "status" | "reschedule" | "edit" | "feedback">("view");
  const id = useId();
  const link = safeLink(i.meeting_url);
  const done = (text: string) => (next: RecInterview, notices?: Notices) => {
    setMode("view");
    onChanged(next, [text, noticeText(notices)].filter(Boolean).join(" "));
  };
  const feedbackSaved = (next: RecInterview) => {
    setMode("view");
    const suggested = next.feedback?.next_round_label;
    onChanged(next, suggested ? `Feedback saved. Next round suggested: ${suggested}.` : "Feedback saved.", next.feedback?.next_round ?? undefined);
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
      {i.feedback && mode !== "feedback" && <FeedbackSummary code={i.code} feedback={i.feedback} />}
      {mode === "feedback" && <FeedbackForm interview={i} onCancel={() => setMode("view")} onSaved={feedbackSaved} />}
      {mode === "view" && (i.allowed_statuses.length > 0 || i.can_reschedule || i.can_edit || i.can_feedback) && (
        <div className="actions" style={{ flexWrap: "wrap" }}>
          {i.allowed_statuses.length > 0 && (
            <button type="button" className="btn small" onClick={() => setMode("status")}>Change status<span className="visually-hidden"> of {i.code}</span></button>
          )}
          {i.can_reschedule && (
            <button type="button" className="btn secondary small" onClick={() => setMode("reschedule")}>Reschedule<span className="visually-hidden"> {i.code}</span></button>
          )}
          {i.can_edit && <button type="button" className="btn secondary small" onClick={() => setMode("edit")}>Edit<span className="visually-hidden"> {i.code}</span></button>}
          {i.can_feedback && (
            <button type="button" className={i.feedback ? "btn secondary small" : "btn small"} onClick={() => setMode("feedback")}>
              {i.feedback ? "Edit feedback" : "Record feedback"}<span className="visually-hidden"> for {i.code}</span>
            </button>
          )}
        </div>
      )}
    </li>
  );
}

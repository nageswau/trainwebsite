"use client";
import { type FormEvent, useCallback, useEffect, useId, useRef, useState } from "react";

import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson } from "@/lib/apiErrors";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import { formatSchoolDateTime } from "@/lib/formatDate";
import {
  ATTENDANCE,
  experienceText,
  isMyInterview,
  MY_LIMIT,
  MY_VIEWS,
  type MyInterview,
  type MyInterviewsPage,
  type MyView,
  myInterviewsUrl,
  myInterviewUrl,
  NOTES_MAX,
  RECOMMENDATIONS,
} from "@/lib/interviewerWorkspace";
import { safeLink } from "@/lib/recruiterCompanies";
import type { PanelFeedback } from "@/lib/recruiterInterviews";

const SIGN_IN = "/it/login";
const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;
const LOAD_FAILED = "Your interviews could not be loaded. Try again.";
type Failure = { message: string; session: boolean };

function whenText(i: MyInterview): string {
  const from = formatSchoolDateTime(i.scheduled_at, true);
  return i.ends_at ? `${from} – ${formatSchoolDateTime(i.ends_at, true)}` : from;
}

/** hrc-029 (DEC-SCOPE-405 V7): attendance, score, recommendation and notes -- the whole form replaces the member's saved feedback. */
function FeedbackForm({ interview, onSaved, onCancel }: { interview: MyInterview; onSaved: (next: MyInterview) => void; onCancel: () => void }) {
  const id = useId();
  const saved = interview.feedback;
  const [attendance, setAttendance] = useState<PanelFeedback["attendance"]>(saved?.attendance ?? "attended");
  const [score, setScore] = useState(saved?.score ? String(saved.score) : "");
  const [recommendation, setRecommendation] = useState(saved?.recommendation ?? "");
  const [notes, setNotes] = useState(saved?.notes ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<Failure | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a fast double click must not send twice
  const attended = attendance === "attended";
  const aria = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${id}-${key}-error` : undefined });

  async function submit(event: FormEvent) {
    event.preventDefault();
    const missing: Record<string, string> = {};
    if (attended && !score) missing.score = "Choose a score";
    if (attended && !recommendation) missing.recommendation = "Choose a recommendation";
    if (Object.keys(missing).length) return setErrors(missing);
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setFailure(null);
    const result = await sendJson(myInterviewUrl(interview.id, "feedback"), "PUT", {
      attendance, score: attended ? Number(score) : null, recommendation: attended ? recommendation : null, notes: notes.trim() || null,
    });
    inFlight.current = false;
    setBusy(false);
    if (result.ok) return isMyInterview(result.data) ? onSaved(result.data) : setFailure({ message: SAVE_FAILED, session: false });
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    const kind = writeFailure(result.status);
    setFailure({ message: kind === "session" ? SESSION_ENDED : kind === "retry" ? SAVE_FAILED : result.message, session: kind === "session" });
  }

  return (
    <form aria-label={`Feedback for ${interview.code}`} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "flex", flexWrap: "wrap", gap: 12 }}>
        <legend style={{ fontWeight: 600, marginBottom: 4 }}>Attendance (required)</legend>
        {ATTENDANCE.map(([key, label]) => (
          <label key={key} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <input type="radio" name={`${id}-attendance`} value={key} checked={attendance === key} onChange={() => { setAttendance(key); setErrors({}); }} />
            {label}
          </label>
        ))}
      </fieldset>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(min(13rem, 100%), 1fr))" }}>
        <div className="field">
          <label htmlFor={`${id}-score`}>Score{attended ? " (required)" : ""}</label>
          <select id={`${id}-score`} value={attended ? score : ""} onChange={(e) => setScore(e.target.value)} disabled={!attended} {...aria("score")}>
            <option value="">Choose a score</option>
            {["1", "2", "3", "4", "5"].map((s) => <option key={s} value={s}>{s} / 5</option>)}
          </select>
          {errors.score && <p id={`${id}-score-error`} className="form-error">{errors.score}</p>}
        </div>
        <div className="field">
          <label htmlFor={`${id}-recommendation`}>Recommendation{attended ? " (required)" : ""}</label>
          <select id={`${id}-recommendation`} value={attended ? recommendation : ""} onChange={(e) => setRecommendation(e.target.value)} disabled={!attended} {...aria("recommendation")}>
            <option value="">Choose a recommendation</option>
            {RECOMMENDATIONS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
          {errors.recommendation && <p id={`${id}-recommendation-error`} className="form-error">{errors.recommendation}</p>}
        </div>
      </div>
      <div className="field">
        <label htmlFor={`${id}-notes`}>Notes</label>
        <textarea id={`${id}-notes`} rows={3} maxLength={NOTES_MAX} value={notes} onChange={(e) => setNotes(e.target.value)} {...aria("notes")} />
        {errors.notes && <p id={`${id}-notes-error`} className="form-error">{errors.notes}</p>}
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>Your feedback goes to the recruiter only. The candidate never sees it.</p>
      {failure && (
        <div role="alert">
          <p className="form-error">{failure.message}</p>
          {failure.session && <ReturnToLoginLink loginHref={SIGN_IN} />}
        </div>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save feedback"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function FeedbackSummary({ code, feedback: f }: { code: string; feedback: PanelFeedback }) {
  const rows: [string, string][] = [
    ["Attendance", f.attendance_label],
    ...(f.score !== null ? [["Score", `${f.score} / 5`] as [string, string]] : []),
    ...(f.recommendation_label ? [["Recommendation", f.recommendation_label] as [string, string]] : []),
    ...(f.notes ? [["Notes", f.notes] as [string, string]] : []),
  ];
  return (
    <div style={{ display: "grid", gap: 2 }}>
      <strong style={{ fontSize: 13 }}>Your feedback</strong>
      <ul aria-label={`Your feedback for ${code}`} style={{ margin: 0, paddingLeft: 18, fontSize: 13, display: "grid", gap: 2 }}>
        {rows.map(([name, value]) => <li key={name}><span className="muted">{name}:</span> <span style={TEXT}>{value}</span></li>)}
      </ul>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>Saved {formatSchoolDateTime(f.updated_at, true)}</p>
    </div>
  );
}

function InterviewCard({ interview: i, onSaved }: { interview: MyInterview; onSaved: (next: MyInterview) => void }) {
  const id = useId();
  const [editing, setEditing] = useState(false);
  const link = safeLink(i.meeting_url);
  const round = i.round_label && i.round_number ? `${i.round_label} (round ${i.round_number})` : i.round_label;
  const facts = ([
    ["Requirement", `${i.requirement.title} · ${i.company.name}`],
    ["When", whenText(i)],
    round && ["Round", round],
    ["Mode", i.mode],
    i.platform_label && ["Platform", i.platform_label],
    i.location && ["Location", i.location],
    i.phone_details && ["Phone", i.phone_details],
    i.instructions && ["Instructions", i.instructions],
  ].filter(Boolean)) as [string, string][];
  const c = i.candidate;
  const profile = ([
    c.location && ["Location", c.location],
    c.qualification && ["Qualification", c.qualification],
    experienceText(c.experience_months) && ["Experience", experienceText(c.experience_months)],
    c.current_company && ["Current company", c.current_company],
    c.skills.length > 0 && ["Skills", c.skills.join(", ")],
  ].filter(Boolean)) as [string, string][];
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-title`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <h4 id={`${id}-title`} style={{ margin: 0 }}>{c.name}</h4>
        <span className="muted" style={{ fontSize: 13 }}>{c.code} · {i.code}</span>
        <span className="badge">{i.status_label}</span>
        {i.is_lead && <span className="badge">Lead interviewer</span>}
        {i.feedback_overdue && <span className="badge" style={{ background: "#fde8e8", color: "#9b1c1c" }}>Feedback overdue</span>}
      </div>
      {i.status === "cancelled" && i.cancel_reason && <p style={{ margin: 0, ...TEXT }}><strong>Cancelled — {i.cancel_reason}</strong></p>}
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(10rem, 100%), 1fr))", gap: "4px 16px", margin: 0 }}>
        {facts.map(([term, value]) => (
          <div key={term}><dt className="muted" style={{ fontSize: 13 }}>{term}</dt><dd style={{ margin: 0, ...TEXT }}>{value}</dd></div>
        ))}
      </dl>
      {profile.length > 0 && (
        <section aria-label={`Candidate summary for ${i.code}`}>
          <strong style={{ fontSize: 13 }}>Candidate summary</strong>
          <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(10rem, 100%), 1fr))", gap: "4px 16px", margin: 0 }}>
            {profile.map(([term, value]) => (
              <div key={term}><dt className="muted" style={{ fontSize: 13 }}>{term}</dt><dd style={{ margin: 0, ...TEXT }}>{value}</dd></div>
            ))}
          </dl>
        </section>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
        {link && <a href={link} target="_blank" rel="noopener noreferrer">Meeting link<span className="visually-hidden"> for {i.code} (opens in a new tab)</span></a>}
        {i.has_resume
          ? <a href={myInterviewUrl(i.id, "resume")} download>Download resume<span className="visually-hidden"> of {c.name}</span></a>
          : <span className="muted" style={{ fontSize: 13 }}>No resume shared</span>}
      </div>
      {i.feedback && !editing && <FeedbackSummary code={i.code} feedback={i.feedback} />}
      {editing && <FeedbackForm interview={i} onCancel={() => setEditing(false)} onSaved={(next) => { setEditing(false); onSaved(next); }} />}
      {!editing && i.can_feedback && (
        <div className="actions">
          <button type="button" className={i.feedback ? "btn secondary small" : "btn small"} onClick={() => setEditing(true)}>
            {i.feedback ? "Edit feedback" : "Submit feedback"}<span className="visually-hidden"> for {i.code}</span>
          </button>
        </div>
      )}
      {!editing && !i.can_feedback && !i.feedback && i.status !== "cancelled" && new Date(i.scheduled_at) > new Date() && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Feedback opens once the interview time has passed.</p>
      )}
    </li>
  );
}

/** hrc-029 (V6, V12): "My interviews" -- the interviews assigned to the signed-in internal interviewer or employer user. */
export default function InterviewerWorkspace({ heading = "My interviews" }: { heading?: string }) {
  const [view, setView] = useState<MyView>("upcoming");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<MyInterviewsPage | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [message, setMessage] = useState("");

  const load = useCallback(async (v: MyView, o: number) => {
    setPage(null);
    setFailure(null);
    try {
      const response = await fetch(myInterviewsUrl(v, o), { cache: "no-store" });
      if (response.status === 401) return setFailure({ message: SESSION_ENDED, session: true });
      if (!response.ok) return setFailure({ message: LOAD_FAILED, session: false });
      setPage((await response.json()) as MyInterviewsPage);
    } catch {
      setFailure({ message: LOAD_FAILED, session: false });
    }
  }, []);

  useEffect(() => { void load(view, offset); }, [load, view, offset]);

  function choose(next: MyView) {
    setMessage("");
    setView(next);
    setOffset(0);
  }

  function saved(next: MyInterview) {
    setPage((p) => (p ? { ...p, items: p.items.map((i) => (i.id === next.id ? next : i)) } : p));
    setMessage(`Feedback saved for ${next.candidate.name}.`);
  }

  return (
    <section className="card" aria-labelledby="my-interviews-heading" style={{ display: "grid", gap: 12 }}>
      <h3 id="my-interviews-heading" style={{ margin: 0 }}>{heading}</h3>
      <div role="group" aria-label="Interview views" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {MY_VIEWS.map(([key, label]) => (
          <button key={key} type="button" className={view === key ? "btn small" : "btn secondary small"} aria-pressed={view === key} onClick={() => choose(key)}>
            {label}{page ? ` (${page.counts[key]})` : ""}
          </button>
        ))}
      </div>
      <p role="status" aria-live="polite" className="form-message" style={{ margin: 0, minHeight: message ? undefined : 0 }}>{message}</p>
      {failure ? (
        <div role="alert">
          <p className="form-error">{failure.message}</p>
          {failure.session ? <ReturnToLoginLink loginHref={SIGN_IN} /> : <button type="button" className="btn secondary small" onClick={() => void load(view, offset)}>Try again</button>}
        </div>
      ) : page === null ? (
        <p className="muted" aria-busy="true">Loading your interviews…</p>
      ) : page.items.length === 0 ? (
        <p className="muted">{view === "upcoming" ? "No interviews are assigned to you yet." : "No past interviews."}</p>
      ) : (
        <>
          <ul style={{ margin: 0, padding: 0, display: "grid", gap: 12 }} aria-label={`${view === "upcoming" ? "Upcoming" : "Past"} interviews`}>
            {page.items.map((i) => <InterviewCard key={i.id} interview={i} onSaved={saved} />)}
          </ul>
          {page.total > MY_LIMIT && (
            <div className="actions">
              <button type="button" className="btn secondary small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - MY_LIMIT))}>Previous</button>
              <span className="muted" style={{ fontSize: 13 }}>{offset + 1}–{Math.min(offset + MY_LIMIT, page.total)} of {page.total}</span>
              <button type="button" className="btn secondary small" disabled={offset + MY_LIMIT >= page.total} onClick={() => setOffset(offset + MY_LIMIT)}>Next</button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

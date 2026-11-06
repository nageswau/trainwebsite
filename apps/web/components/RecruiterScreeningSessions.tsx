"use client";
import { type FormEvent, useCallback, useEffect, useId, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import {
  COMPENSATION,
  failedKnockouts,
  type FormQuestion,
  isSessionsRead,
  LIMITS,
  RATINGS,
  SCORES,
  scoreText,
  type ScreeningForm,
  type Session,
  type SessionsRead,
  sessionsUrl,
  yesNoLabel,
} from "@/lib/recruiterScreening";

const NEEDS_REASON = "Give a reason for overriding the knock-out.";
const CHECKLIST_LABELS: [string, string][] = [
  ["qualification_verified", "Qualification verified"], ["experience_verified", "Experience verified"], ["skills_verified", "Skills verified"],
  ["expected_salary", "Expected salary"], ["notice_days", "Notice (days)"], ["location_preference", "Location preference"], ["availability", "Availability"],
  ["communication_rating", "Communication"], ["technical_rating", "Technical"], ["willing_to_relocate", "Willing to relocate"],
];
const checklistValue = (value: unknown) => (value === true ? "Yes" : value === false ? "No" : String(value));
const field = { display: "grid", gap: 4 } as const;
const small = { margin: 0, fontSize: 13 } as const;

function AnswerInput({ question, id, value, onChange }: { question: FormQuestion; id: string; value: string; onChange: (v: string) => void }) {
  const shared = { id, value, onChange: (e: { target: { value: string } }) => onChange(e.target.value) };
  if (question.format === "text") return <textarea {...shared} rows={2} maxLength={LIMITS.answer} />;
  if (question.format === "numeric") return <input {...shared} type="number" step="any" inputMode="decimal" />;
  const options = question.format === "yes_no" ? ["yes", "no"] : question.format === "rating" ? RATINGS : question.choices ?? [];
  return (
    <select {...shared}>
      <option value="">Not answered</option>
      {options.map((o) => <option key={o} value={o}>{question.format === "yes_no" ? yesNoLabel(o) : o}</option>)}
    </select>
  );
}

/** rec-018's panel pattern: one record, saved whole. A knock-out warning is a hint; the API decides the recommendation again (S8). */
function Runner({ form, data, applicationId, onSaved, onStale, onCancel }: {
  form: ScreeningForm; data: SessionsRead; applicationId: string; onSaved: () => void; onStale: (message: string) => void; onCancel: () => void;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [scores, setScores] = useState<Record<string, string>>({});
  const [recommendation, setRecommendation] = useState("");
  const [notes, setNotes] = useState("");
  const [override, setOverride] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const sending = useRef(false); // a fast double click lands before `busy` re-renders the button disabled
  const id = useId();
  const questions = data.sees_compensation ? form.questions : form.questions.filter((q) => q.category !== COMPENSATION);
  const failed = failedKnockouts(form, answers);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (sending.current) return;
    const overriding = override && failed.length > 0;
    if (overriding && !reason.trim()) return setFailure(NEEDS_REASON);
    sending.current = true;
    setBusy(true);
    setFailure(null);
    const rows = questions.filter((q) => answers[q.id]?.trim()).map((q) => ({ question_id: q.id, answer: answers[q.id].trim(), ...(scores[q.id] ? { score: Number(scores[q.id]) } : {}) }));
    const outcome = await sendJson(sessionsUrl(applicationId), "POST", {
      form_version: form.version, answers: rows, notes: notes.trim() || null, recommendation, knockout_override: overriding, override_reason: overriding ? reason.trim() : null,
    });
    sending.current = false;
    setBusy(false);
    if (outcome.ok) return onSaved();
    setFailure(outcome.message);
    if (outcome.status === 409) onStale(outcome.message);
  }

  return (
    <form onSubmit={submit} aria-label="Record a screening session" style={{ display: "grid", gap: 10 }}>
      <p className="muted" style={small}>{form.name} · version {form.version}</p>
      {form.knockout_status === "pending" && <p className="muted" style={small}>Knock-out questions are awaiting Team Lead approval, so they count as ordinary questions for now.</p>}
      {!data.sees_compensation && questions.length < form.questions.length && <p className="muted" style={small}>Compensation questions are left for a colleague with salary access.</p>}
      {questions.map((q) => (
        <div key={q.id} style={{ display: "grid", gap: 6 }}>
          <div style={field}>
            <label htmlFor={`${id}-${q.id}`} style={{ overflowWrap: "anywhere" }}>
              {q.text}
              {q.is_knockout && <span className="badge" style={{ marginLeft: 6 }}>Knock-out</span>}
            </label>
            <span className="muted" style={{ fontSize: 12 }}>
              {q.category_label}{q.evaluation_criteria && <> · Look for: {q.evaluation_criteria}</>}{q.expected_answer && <> · Expected: {q.is_knockout ? yesNoLabel(q.expected_answer) : q.expected_answer}</>}
            </span>
            <AnswerInput question={q} id={`${id}-${q.id}`} value={answers[q.id] ?? ""} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))} />
          </div>
          {q.format !== "rating" && (
            <label htmlFor={`${id}-${q.id}-score`} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>
              <span>Score<span className="visually-hidden"> for {q.text}</span></span>
              <select id={`${id}-${q.id}-score`} value={scores[q.id] ?? ""} onChange={(e) => setScores((s) => ({ ...s, [q.id]: e.target.value }))}>
                <option value="">No score</option>
                {SCORES.map((s) => <option key={s} value={s}>{s} / 5</option>)}
              </select>
            </label>
          )}
        </div>
      ))}
      {failed.length > 0 && (
        <div role="alert" className="form-error" style={{ display: "grid", gap: 6 }}>
          <span>A knock-out failed ({failed.map((q) => q.text).join(", ")}). This session will be saved as Reject unless you override it.</span>
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} /> Override the knock-out
          </label>
          {override && (
            <label htmlFor={`${id}-reason`} style={field}>
              Reason for the override
              <input id={`${id}-reason`} maxLength={LIMITS.reason} value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
          )}
        </div>
      )}
      <label htmlFor={`${id}-recommendation`} style={field}>
        Recommendation
        <select id={`${id}-recommendation`} required value={recommendation} onChange={(e) => setRecommendation(e.target.value)}>
          <option value="">Choose a recommendation</option>
          {data.recommendations.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
        </select>
      </label>
      <label htmlFor={`${id}-notes`} style={field}>
        Notes (internal)
        <textarea id={`${id}-notes`} rows={2} maxLength={LIMITS.notes} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <p className="muted" style={small}>A recommendation does not change the candidate&apos;s status. Use Change status when you are ready.</p>
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || !recommendation}>{busy ? "Saving…" : "Save session"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function SessionItem({ session }: { session: Session }) {
  const checklist = session.checklist;
  return (
    <li className="action-card" style={{ gap: 4 }}>
      <p style={{ ...small, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "baseline" }}>
        <strong>{session.recommendation_label}</strong>
        {session.kind === "form" ? <span>{scoreText(session.scorecard)}</span> : <span>Checklist: {checklist?.result_label}</span>}
        {session.knockout_triggered && <span className="badge">{session.knockout_overridden ? "Knock-out overridden" : "Knock-out failed"}</span>}
      </p>
      <p className="muted" style={small}>
        {session.screened_by.full_name} · <LocalTime value={session.created_at} time />{session.form_version !== null && <> · Form version {session.form_version}</>}
      </p>
      {session.override_reason && <p style={{ ...small, overflowWrap: "anywhere" }}>Override reason: {session.override_reason}</p>}
      {session.answers.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, display: "grid", gap: 2 }}>
          {session.answers.map((a) => (
            <li key={a.question_id} style={{ overflowWrap: "anywhere" }}>
              <span className="muted">{a.question}</span>{" "}
              <span>{a.answer_hidden ? "Hidden" : a.format === "yes_no" ? yesNoLabel(a.answer) : a.answer}</span>
              {a.score !== null && <span className="muted"> ({a.score} / 5)</span>}
            </li>
          ))}
        </ul>
      )}
      {checklist && (
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, display: "grid", gap: 2 }}>
          {CHECKLIST_LABELS.filter(([key]) => checklist[key] !== undefined && checklist[key] !== null).map(([key, label]) => (
            <li key={key} style={{ overflowWrap: "anywhere" }}><span className="muted">{label}:</span> {checklistValue(checklist[key])}</li>
          ))}
        </ul>
      )}
      {session.notes && <p style={{ ...small, overflowWrap: "anywhere", whiteSpace: "pre-line" }}><span className="muted">Notes:</span> {session.notes}</p>}
    </li>
  );
}

/** pob-020 (DEC-SCOPE-414): the application's kept screening sessions and, for a writer on an open application, the runner. The rec-018
 *  checklist stays below it in the same panel. */
export default function RecruiterScreeningSessions({ applicationId, candidateName }: { applicationId: string; candidateName: string }) {
  const [data, setData] = useState<SessionsRead | null>(null);
  const [failed, setFailed] = useState(false);
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null); // a 409 outlives the runner when the reload closes it

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch(sessionsUrl(applicationId), { signal });
      const body = response.ok ? await response.json() : null;
      if (isSessionsRead(body)) setData(body);
      else setFailed(true);
    } catch {
      if (!signal?.aborted) setFailed(true);
    }
  }, [applicationId]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  if (failed) return <p className="form-error" role="alert" style={small}>Unable to load the screening sessions.</p>;
  if (data === null) return <p className="muted" role="status" style={small}>Loading screening sessions…</p>;

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <h4 style={{ margin: 0 }}>Screening sessions</h4>
      {notice && <p role="status" style={small}>{notice}</p>}
      {data.form === null && <p className="muted" style={small}>This requirement has no screening form yet. Create one in the requirement&apos;s Screening form section.</p>}
      {data.can_run && data.form && !running && (
        <div className="actions"><button type="button" className="btn small" onClick={() => { setRunning(true); setNotice(null); }}>Record a session<span className="visually-hidden"> for {candidateName}</span></button></div>
      )}
      {conflict && !(running && data.can_run) && <p className="form-error" role="alert" style={{ margin: 0 }}>{conflict}</p>}
      {running && data.can_run && data.form && (
        <Runner form={data.form} data={data} applicationId={applicationId} onCancel={() => { setRunning(false); setConflict(null); }} onStale={(message) => { setConflict(message); void load(); }}
          onSaved={() => { setRunning(false); setConflict(null); setNotice("Session recorded."); void load(); }} />
      )}
      {data.sessions.length === 0
        ? <p className="muted" style={small}>No screening sessions yet.</p>
        : <ul aria-label={`Screening sessions of ${candidateName}`} style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 6 }}>{data.sessions.map((s) => <SessionItem key={s.id} session={s} />)}</ul>}
    </div>
  );
}

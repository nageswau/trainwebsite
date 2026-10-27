"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import LocalTime from "@/components/LocalTime";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import {
  emptyForm,
  Interview,
  INTERVIEW_MODES,
  INTERVIEW_OUTCOMES,
  InterviewForm,
  interviewBody,
  interviewProblem,
  interviewsUrl,
  interviewUrl,
  LOCATION_MAX,
  meetingLink,
  MODE_LABELS,
  NOTE_MAX,
  OUTCOME_LABELS,
  toForm,
} from "@/lib/applicationInterviews";

// readOnly: a withdrawn or closed application, whose writes the server refuses (I6).
type Props = { applicationId: string; readOnly?: boolean; onChanged: (message: string) => void };
// null: not editing; "new": the add form; otherwise the id of the interview being edited.
type Editing = null | "new" | string;
const OUTCOME_CLASS: Record<string, string> = { "": "pending", passed: "", not_successful: "error", cancelled: "closed" };

export function InterviewSummary({ interview: i }: { interview: Interview }) {
  const link = meetingLink(i.location);
  return (
    <>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        <strong>
          <LocalTime value={i.scheduled_at} time />
        </strong>
        <span className="badge">{i.mode_label}</span>
        <span className={`status ${OUTCOME_CLASS[i.outcome ?? ""]}`}>{i.outcome_label}</span>
      </div>
      {i.location && (
        <p style={{ fontSize: 13, margin: "4px 0 0", overflowWrap: "anywhere" }}>
          {link ? (
            <a href={link} target="_blank" rel="noopener noreferrer">
              {link}
            </a>
          ) : (
            i.location
          )}
        </p>
      )}
      {i.student_note && <p style={{ fontSize: 13, margin: "4px 0 0", whiteSpace: "pre-line" }}>{i.student_note}</p>}
    </>
  );
}

// nehn-037 part 4 (DEC-SCOPE-296): an application's admission interviews on the counselor's application card -- add one, change it,
// record its result. Everything here is shown to the student (I8). The server checks every rule and the scope again.
export default function ApplicationInterviewsPanel({ applicationId, readOnly = false, onChanged }: Props) {
  const [items, setItems] = useState<Interview[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const [form, setForm] = useState<InterviewForm>(emptyForm());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a same-tick second submit sends nothing

  async function load() {
    setLoadError(null);
    const outcome = await sendRequest(interviewsUrl(applicationId), {});
    if (!outcome.ok) return setLoadError(outcome.message);
    setItems((outcome.data as unknown as { interviews: Interview[] }).interviews ?? []);
  }

  useEffect(() => {
    load();
  }, [applicationId]); // eslint-disable-line react-hooks/exhaustive-deps -- reload only when the application changes

  function open(target: Editing, interview?: Interview) {
    setEditing(target);
    setForm(interview ? toForm(interview) : emptyForm());
    setError(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || editing === null) return;
    const problem = interviewProblem(form);
    if (problem) return setError(problem);
    const saved = editing === "new" ? undefined : items?.find((i) => i.id === editing);
    const body = interviewBody(form, saved);
    if (saved && Object.keys(body).length === 0) return setEditing(null);
    inFlight.current = true;
    setBusy(true);
    setError(null);
    let outcome: Awaited<ReturnType<typeof sendJson>>;
    try {
      outcome = saved ? await sendJson(interviewUrl(applicationId, saved.id), "PATCH", body) : await sendJson(interviewsUrl(applicationId), "POST", body);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
    if (!outcome.ok) return setError(outcome.message);
    setEditing(null);
    onChanged("Interview saved.");
    await load();
  }

  if (loadError) {
    return (
      <div className="form-error" role="alert" style={{ marginTop: 8 }}>
        {loadError}{" "}
        <button type="button" className="btn ghost small" onClick={load}>
          Try again
        </button>
      </div>
    );
  }
  if (items === null) return <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>Loading interviews…</p>;

  const id = (name: string) => `interview-${name}-${applicationId}`;
  const editor = (
    <form className="form" onSubmit={submit} aria-label={editing === "new" ? "Add an interview" : "Edit the interview"} style={{ marginTop: 8 }} noValidate>
      <div className="form-grid">
        <div className="field">
          <label htmlFor={id("when")}>Date and time</label>
          <input id={id("when")} type="datetime-local" required aria-required="true" value={form.when} onChange={(e) => setForm({ ...form, when: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor={id("mode")}>Mode</label>
          <select id={id("mode")} value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })}>
            {INTERVIEW_MODES.map((mode) => (
              <option key={mode} value={mode}>
                {MODE_LABELS[mode]}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor={id("location")}>Link or place</label>
          <input id={id("location")} type="text" maxLength={LOCATION_MAX} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor={id("outcome")}>Result</label>
          <select id={id("outcome")} value={form.outcome} onChange={(e) => setForm({ ...form, outcome: e.target.value })}>
            {["", ...INTERVIEW_OUTCOMES].map((outcome) => (
              <option key={outcome} value={outcome}>
                {OUTCOME_LABELS[outcome]}
              </option>
            ))}
          </select>
          <small className="muted">Passed or not successful only after the interview date.</small>
        </div>
      </div>
      <div className="field">
        <label htmlFor={id("note")}>Note for the student</label>
        <textarea id={id("note")} rows={2} maxLength={NOTE_MAX} value={form.student_note} onChange={(e) => setForm({ ...form, student_note: e.target.value })} />
        <small className="muted">The student sees everything on this interview -- keep internal notes in the student&apos;s notes.</small>
      </div>
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      <div className="actions">
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : "Save interview"}
        </button>
        <button type="button" className="btn ghost small" disabled={busy} onClick={() => setEditing(null)}>
          Cancel
        </button>
      </div>
    </form>
  );

  return (
    <section aria-label="Admission interviews" style={{ marginTop: 8 }}>
      {items.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>No admission interviews recorded yet.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
          {items.map((i) => (
            <li key={i.id} className="card" style={{ padding: 10 }}>
              {editing === i.id ? (
                editor
              ) : (
                <>
                  <InterviewSummary interview={i} />
                  {i.recorded_by && <p className="muted" style={{ fontSize: 12, margin: "4px 0 0" }}>Recorded by {i.recorded_by}</p>}
                  {!readOnly && (
                    <button type="button" className="btn ghost small" style={{ marginTop: 6 }} disabled={busy} onClick={() => open(i.id, i)}>
                      Edit interview
                    </button>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {readOnly ? null : editing === "new" ? (
        editor
      ) : (
        <button type="button" className="btn small" style={{ marginTop: 8 }} disabled={busy} onClick={() => open("new")}>
          Add interview
        </button>
      )}
    </section>
  );
}

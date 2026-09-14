"use client";

import { FormEvent, useEffect, useState } from "react";

type JobOption = { id: string; title: string };
type CandidateOption = { student_id: string; name: string };
type ShortlistRow = { id: string; candidate: string; job_title: string; status: string };
type InterviewRow = { id: string; candidate: string; job_title: string; scheduled_at: string; mode: string; result: string | null };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to complete this action.";
}

// EMP-004: no endpoint or UI let an Employer shortlist a candidate or schedule an
// interview at all. Shortlisting reuses `JobApplication` (status "shortlisted") against
// one of the Employer's own postings rather than inventing a parallel table. Scheduling
// an interview for a candidate who already has one at the exact same instant is
// rejected (409), not silently double-booked (EMP-004-AC02) -- surfaced here as a
// per-row error, never hidden.
export default function EmployerInterviewsPanel() {
  const [jobs, setJobs] = useState<JobOption[]>([]);
  const [candidates, setCandidates] = useState<CandidateOption[]>([]);
  const [shortlist, setShortlist] = useState<ShortlistRow[] | null>(null);
  const [interviews, setInterviews] = useState<InterviewRow[] | null>(null);
  const [shortlistMessage, setShortlistMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [scheduleMessage, setScheduleMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  function load() {
    fetch("/api/v1/employer/jobs").then((r) => (r.ok ? r.json() : [])).then(setJobs);
    fetch("/api/v1/employer/candidates").then((r) => (r.ok ? r.json() : [])).then(setCandidates);
    fetch("/api/v1/employer/shortlist").then((r) => (r.ok ? r.json() : [])).then(setShortlist);
    fetch("/api/v1/employer/interviews").then((r) => (r.ok ? r.json() : [])).then(setInterviews);
  }

  useEffect(load, []);

  async function shortlistCandidate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setShortlistMessage(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/v1/employer/shortlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: form.get("job_id"), student_id: form.get("student_id") }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setShortlistMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setShortlistMessage({ text: "Candidate shortlisted.", failed: false });
    load();
  }

  async function scheduleInterview(event: FormEvent<HTMLFormElement>, applicationId: string) {
    event.preventDefault();
    setBusyId(applicationId);
    setScheduleMessage(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/v1/employer/interviews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ application_id: applicationId, scheduled_at: form.get("scheduled_at") }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setScheduleMessage({ id: applicationId, text: detailMessage(data.detail), failed: true });
      return;
    }
    setScheduleMessage({ id: applicationId, text: "Interview scheduled.", failed: false });
    load();
  }

  return (
    <div className="action-card">
      <h3>Shortlist &amp; Interviews</h3>
      <form className="form" onSubmit={shortlistCandidate}>
        <div className="field">
          <label htmlFor="shortlist-job">Job posting</label>
          <select id="shortlist-job" name="job_id" required>
            <option value="">Select a posting…</option>
            {jobs.map((job) => (
              <option key={job.id} value={job.id}>{job.title}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="shortlist-candidate">Candidate</label>
          <select id="shortlist-candidate" name="student_id" required>
            <option value="">Select a candidate…</option>
            {candidates.map((candidate) => (
              <option key={candidate.student_id} value={candidate.student_id}>{candidate.name}</option>
            ))}
          </select>
        </div>
        <button className="btn small">Shortlist</button>
      </form>
      {shortlistMessage && (
        <div className={shortlistMessage.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {shortlistMessage.text}
        </div>
      )}

      <h4 style={{ marginTop: 24 }}>Shortlisted candidates</h4>
      {shortlist === null ? (
        <p className="muted">Loading…</p>
      ) : shortlist.length === 0 ? (
        <p className="muted">No candidates shortlisted yet.</p>
      ) : (
        <div className="grid two">
          {shortlist.map((row) => (
            <div className="card" key={row.id}>
              <span className="badge">{row.status}</span>
              <h4 style={{ marginTop: 10 }}>{row.candidate}</h4>
              <p className="muted" style={{ fontSize: 13 }}>{row.job_title}</p>
              <form className="form" onSubmit={(event) => scheduleInterview(event, row.id)}>
                <div className="field">
                  <label htmlFor={`interview-time-${row.id}`}>Interview date/time</label>
                  <input id={`interview-time-${row.id}`} name="scheduled_at" type="datetime-local" required />
                </div>
                <button className="btn small" disabled={busyId === row.id}>{busyId === row.id ? "Scheduling…" : "Schedule interview"}</button>
              </form>
              {scheduleMessage?.id === row.id && (
                <div className={scheduleMessage.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>
                  {scheduleMessage.text}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <h4 style={{ marginTop: 24 }}>Scheduled interviews</h4>
      {interviews === null ? (
        <p className="muted">Loading…</p>
      ) : interviews.length === 0 ? (
        <p className="muted">No interviews scheduled yet.</p>
      ) : (
        <div className="grid two">
          {interviews.map((row) => (
            <div className="card" key={row.id}>
              <span className="badge">{row.result || "Awaiting outcome"}</span>
              <h4 style={{ marginTop: 10 }}>{row.candidate}</h4>
              <p className="muted" style={{ fontSize: 13 }}>{row.job_title} · {row.mode} · {new Date(row.scheduled_at).toLocaleString()}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

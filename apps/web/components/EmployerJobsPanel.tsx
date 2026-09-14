"use client";

import { FormEvent, useEffect, useState } from "react";

type JobRow = { id: string; title: string; location: string; description: string; skills: string[]; status: string; closes_on: string | null; visible_to_students: boolean };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to complete this action.";
}

// EMP-002: no endpoint or UI let an Employer post a job at all -- job creation was
// Placement Team/HR Team/Admin-only. Lists the Employer's own postings (never another
// company's, verified server-side) with a real create form. A posting starts as a
// draft (API_CONTRACT.md #6) -- not visible to students until the Employer publishes it
// themselves (no staff review gate is invented, the same "no invented approval gate"
// precedent as EMP-001's own registration_status). A published posting past its own
// `closes_on` date is marked not-visible-to-students here even if `status` still reads
// "open" (EMP-002-AC02) -- the same rule the public/student listings now enforce
// server-side.
export default function EmployerJobsPanel() {
  const [jobs, setJobs] = useState<JobRow[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);
  const [createMessage, setCreateMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [creating, setCreating] = useState(false);

  function load() {
    fetch("/api/v1/employer/jobs")
      .then((res) => (res.ok ? res.json() : []))
      .then(setJobs)
      .catch(() => setJobs([]));
  }

  useEffect(load, []);

  async function createJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setCreateMessage(null);
    const form = new FormData(event.currentTarget);
    const skills = String(form.get("skills") || "").split(",").map((s) => s.trim()).filter(Boolean);
    const closesOn = String(form.get("closes_on") || "");
    const response = await fetch("/api/v1/employer/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: form.get("title"),
        location: String(form.get("location") || "Remote"),
        description: String(form.get("description") || ""),
        skills,
        closes_on: closesOn || null,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setCreating(false);
    if (!response.ok) {
      setCreateMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setCreateMessage({ text: "Job posted.", failed: false });
    (event.target as HTMLFormElement).reset();
    load();
  }

  async function setStatus(jobId: string, status: "open" | "closed") {
    setBusyId(jobId);
    setMessage(null);
    const response = await fetch(`/api/v1/employer/jobs/${jobId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: jobId, text: detailMessage(data.detail), failed: true });
      return;
    }
    load();
  }

  return (
    <div className="action-card">
      <h3>Post a Job</h3>
      <form className="form" onSubmit={createJob}>
        <div className="field">
          <label htmlFor="job-title">Title</label>
          <input id="job-title" name="title" required />
        </div>
        <div className="field">
          <label htmlFor="job-location">Location</label>
          <input id="job-location" name="location" defaultValue="Remote" />
        </div>
        <div className="field">
          <label htmlFor="job-description">Description</label>
          <textarea id="job-description" name="description" />
        </div>
        <div className="field">
          <label htmlFor="job-skills">Skills (comma separated)</label>
          <input id="job-skills" name="skills" placeholder="Python, FastAPI, PostgreSQL" />
        </div>
        <div className="field">
          <label htmlFor="job-closes-on">Closing date (optional)</label>
          <input id="job-closes-on" name="closes_on" type="date" />
        </div>
        <button className="btn small" disabled={creating}>{creating ? "Posting…" : "Post job"}</button>
      </form>
      {createMessage && (
        <div className={createMessage.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {createMessage.text}
        </div>
      )}

      <h4 style={{ marginTop: 24 }}>Your postings</h4>
      {jobs === null ? (
        <p className="muted">Loading your postings…</p>
      ) : jobs.length === 0 ? (
        <p className="muted">You have not posted any jobs yet.</p>
      ) : (
        <div className="grid two">
          {jobs.map((job) => (
            <div className="card" key={job.id}>
              <span className="badge">{job.visible_to_students ? "Visible to students" : job.status === "draft" ? "Draft" : job.status === "closed" ? "Closed" : "Expired"}</span>
              <h4 style={{ marginTop: 10 }}>{job.title}</h4>
              <p className="muted" style={{ fontSize: 13 }}>{job.location}{job.closes_on ? ` · Closes ${job.closes_on}` : ""}</p>
              {job.status === "draft" && (
                <button className="btn small" disabled={busyId === job.id} onClick={() => setStatus(job.id, "open")}>
                  {busyId === job.id ? "Publishing…" : "Publish"}
                </button>
              )}
              {job.status === "open" && (
                <button className="btn small" disabled={busyId === job.id} onClick={() => setStatus(job.id, "closed")}>
                  {busyId === job.id ? "Closing…" : "Close posting"}
                </button>
              )}
              {message?.id === job.id && (
                <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>
                  {message.text}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

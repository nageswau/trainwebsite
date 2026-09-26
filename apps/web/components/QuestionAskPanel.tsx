"use client";

import { FormEvent, useEffect, useState } from "react";

import LocalTime from "@/components/LocalTime";

type CourseRow = { batch_id: string; program: string; batch: string };
type Reply = { id: string; author_id: string; body: string; created_at: string };
type ThreadRow = { id: string; batch_id: string; subject: string; body: string; replies: Reply[] };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to submit your question.";
}

// TRN-009: "Trainer answers a question; Student sees the reply." No Q&A model or
// endpoint existed anywhere before this (DATA_MODEL.md's own "carries over" note for
// QuestionThread/QuestionReply did not hold, same pattern already found for STU-005 and
// STU-008). Lists the student's own threads with every reply inline, and lets them raise
// a new question against a batch they're actually enrolled in -- the only valid target,
// per this feature's own AC.
export default function QuestionAskPanel() {
  const [batches, setBatches] = useState<CourseRow[] | null>(null);
  const [threads, setThreads] = useState<ThreadRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  function load() {
    fetch("/api/v1/workflows/it/student/questions")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setThreads(data))
      .catch(() => setThreads([]));
  }

  useEffect(() => {
    fetch("/api/v1/portal/it/student/course")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => setBatches(data.rows || []))
      .catch(() => setBatches([]));
    load();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setFailed(false);
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const response = await fetch("/api/v1/workflows/it/student/questions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ batch_id: form.get("batch_id"), subject: form.get("subject"), body: form.get("body") }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setFailed(true);
      setMessage(detailMessage(data.detail));
      return;
    }
    setMessage("Question submitted.");
    formElement.reset();
    load();
  }

  if (batches === null || threads === null) {
    return (
      <div className="action-card">
        <h3>My Questions</h3>
        <p className="muted">Loading your questions…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>My Questions</h3>
      {threads.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          {threads.map((thread) => (
            <div className="card" key={thread.id} style={{ marginBottom: 12 }}>
              <h4>{thread.subject}</h4>
              <p style={{ fontSize: 13 }}>{thread.body}</p>
              {thread.replies.length === 0 ? (
                <p className="muted" style={{ fontSize: 13 }}>Awaiting a reply from your trainer.</p>
              ) : (
                <ul>
                  {thread.replies.map((reply) => (
                    <li key={reply.id} style={{ fontSize: 13 }}>
                      <span className="muted"><LocalTime value={reply.created_at} time />:</span> {reply.body}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
      {batches.length === 0 ? (
        <p className="muted">You have no enrolments to ask a question against yet.</p>
      ) : (
        <form className="form" onSubmit={submit}>
          <div className="field">
            <label htmlFor="question-batch">Batch</label>
            <select id="question-batch" name="batch_id" required>
              {batches.map((row) => (
                <option key={row.batch_id} value={row.batch_id}>{row.program} · {row.batch}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="question-subject">Subject</label>
            <input id="question-subject" name="subject" required />
          </div>
          <div className="field">
            <label htmlFor="question-body">Question</label>
            <textarea id="question-body" name="body" required />
          </div>
          {message && <div className={failed ? "form-error" : "form-message"} role="status" aria-live="polite">{message}</div>}
          <button className="btn small" disabled={busy}>{busy ? "Submitting…" : "Ask question"}</button>
        </form>
      )}
    </div>
  );
}

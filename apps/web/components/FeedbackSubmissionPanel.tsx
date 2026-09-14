"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type FeedbackRow = { batch_id: string; program: string; batch: string; status: string };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to submit feedback.";
}

// STU-008: "Submit feedback on a course/trainer... rejected if not enrolled." No feedback
// model or endpoint existed anywhere in the codebase before this (DATA_MODEL.md's own
// "carries over" note for CourseFeedback did not hold, same pattern already found once
// for STU-005). This lists the student's own enrolled batches -- the only valid targets,
// per STU-008-AC03 -- and submits directly against a real `batch_id`, no manual reference
// entry. An anonymous-submission option is an explicitly unconfirmed PRD open item
// (PRD-STU-009) and is not offered here.
export default function FeedbackSubmissionPanel() {
  const router = useRouter();
  const [rows, setRows] = useState<FeedbackRow[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/portal/it/student/feedback")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => !cancelled && setRows(data.rows || []))
      .catch(() => !cancelled && setRows([]));
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>, batchId: string) {
    event.preventDefault();
    setBusyId(batchId);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const rating = Number(form.get("rating"));
    const comments = String(form.get("comments") || "");
    const response = await fetch("/api/v1/workflows/it/student/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ batch_id: batchId, rating, comments: comments || null }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: batchId, text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ id: batchId, text: "Feedback submitted -- thank you.", failed: false });
    setOpenId(null);
    router.refresh();
  }

  if (rows === null) {
    return (
      <div className="action-card">
        <h3>Course Feedback</h3>
        <p className="muted">Loading your enrolled courses…</p>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="action-card">
        <h3>Course Feedback</h3>
        <p className="muted">You have no enrolments to give feedback on yet.</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Course Feedback</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {rows.map((row) => (
          <div className="card" key={row.batch_id}>
            <span className="badge">{row.status}</span>
            <h4 style={{ marginTop: 10 }}>{row.program}</h4>
            <p className="muted" style={{ fontSize: 13 }}>{row.batch}</p>
            {openId === row.batch_id ? (
              <form className="form" onSubmit={(event) => submit(event, row.batch_id)}>
                <div className="field">
                  <label htmlFor={`rating-${row.batch_id}`}>Rating</label>
                  <select id={`rating-${row.batch_id}`} name="rating" defaultValue="5" required>
                    {[5, 4, 3, 2, 1].map((value) => (
                      <option key={value} value={value}>{value} / 5</option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor={`comments-${row.batch_id}`}>Comments</label>
                  <textarea id={`comments-${row.batch_id}`} name="comments" />
                </div>
                <button className="btn small" disabled={busyId === row.batch_id}>
                  {busyId === row.batch_id ? "Submitting…" : "Submit feedback"}
                </button>
              </form>
            ) : (
              <button className="btn small" onClick={() => setOpenId(row.batch_id)}>
                {row.status === "Submitted" ? "Submit feedback again" : "Give feedback"}
              </button>
            )}
            {message?.id === row.batch_id && (
              <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
                {message.text}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

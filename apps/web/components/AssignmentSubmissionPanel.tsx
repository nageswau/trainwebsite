"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type AssignmentRow = { id: string; title: string; due: string; submission: string; score: string | null; feedback: string | null };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to submit.";
}

function formatDue(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

// STU-004: "View assigned work, submit before due date." Previously a student had to
// copy an assignment's raw database reference out of the read-only table above and
// paste it into a disconnected generic form. This fetches the same data the table
// shows and lets a student submit directly against the specific assignment, with the
// correct ID wired automatically -- no manual reference entry.
export default function AssignmentSubmissionPanel({ section }: { section: "assignments" | "projects" }) {
  const router = useRouter();
  const [rows, setRows] = useState<AssignmentRow[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/v1/portal/it/student/${section}`)
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => !cancelled && setRows(data.rows || []))
      .catch(() => !cancelled && setRows([]));
    return () => {
      cancelled = true;
    };
  }, [section]);

  async function submit(event: FormEvent<HTMLFormElement>, assignmentId: string) {
    event.preventDefault();
    setBusyId(assignmentId);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const answer = String(form.get("answer") || "");
    const fileUrl = String(form.get("file_url") || "");
    const response = await fetch(`/api/v1/workflows/it/assignments/${assignmentId}/submissions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer: answer || null, file_url: fileUrl || null }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: assignmentId, text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({
      id: assignmentId,
      text: data.is_late ? "Submitted -- this was after the due date and is marked late." : "Submitted on time.",
      failed: false,
    });
    setOpenId(null);
    router.refresh();
  }

  if (rows === null) {
    return (
      <div className="action-card">
        <h3>Submit work</h3>
        <p className="muted">Loading your assignments…</p>
      </div>
    );
  }

  const pending = rows.filter((row) => row.submission === "not submitted");

  if (pending.length === 0) {
    return (
      <div className="action-card">
        <h3>Submit work</h3>
        <p className="muted">Nothing is currently pending submission.</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Submit work</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {pending.map((row) => (
          <div className="card" key={row.id}>
            <h4>{row.title}</h4>
            <p className="muted" style={{ fontSize: 13 }}>Due {formatDue(row.due)}</p>
            {openId === row.id ? (
              <form className="form" onSubmit={(event) => submit(event, row.id)}>
                <div className="field">
                  <label htmlFor={`answer-${row.id}`}>Answer</label>
                  <textarea id={`answer-${row.id}`} name="answer" />
                </div>
                <div className="field">
                  <label htmlFor={`file-${row.id}`}>File URL (if required)</label>
                  <input id={`file-${row.id}`} name="file_url" />
                </div>
                <button className="btn small" disabled={busyId === row.id}>
                  {busyId === row.id ? "Submitting…" : "Submit"}
                </button>
              </form>
            ) : (
              <button className="btn small" onClick={() => setOpenId(row.id)}>
                Submit this work
              </button>
            )}
            {message?.id === row.id && (
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

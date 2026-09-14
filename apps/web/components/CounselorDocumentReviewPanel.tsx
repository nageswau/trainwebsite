"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type DocumentRow = { id: string; student: string; document: string; status: string; notes: string | null };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to complete this action.";
}

// OVS-005: a Counselor previously had no way to actually view a document at all before
// verifying it (the queue never surfaced a file link, and the only write path was a
// raw-typed document UUID + status dropdown) -- same class of gap already fixed for
// ADM-001/002/003/004/006/007. This lists the Counselor's own assigned document queue
// with a real "View document" download action and Verify/Reject controls.
export default function CounselorDocumentReviewPanel() {
  const router = useRouter();
  const [rows, setRows] = useState<DocumentRow[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  function load() {
    fetch("/api/v1/portal/overseas/counselor/documents")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => setRows(data.rows || []))
      .catch(() => setRows([]));
  }

  useEffect(load, []);

  async function view(row: DocumentRow) {
    setBusyId(row.id);
    setMessage(null);
    const response = await fetch(`/api/v1/workflows/overseas/documents/${row.id}/download`);
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: row.id, text: detailMessage(data.detail), failed: true });
      return;
    }
    window.open(data.url, "_blank", "noreferrer");
  }

  async function submit(event: FormEvent<HTMLFormElement>, documentId: string) {
    event.preventDefault();
    setBusyId(documentId);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch(`/api/v1/workflows/overseas/documents/${documentId}/verify`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verification_status: String(form.get("verification_status")), notes: String(form.get("notes") || "") || null }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: documentId, text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ id: documentId, text: "Document reviewed -- the student has been notified.", failed: false });
    setOpenId(null);
    router.refresh();
    load();
  }

  if (rows === null) {
    return (
      <div className="action-card">
        <h3>Document Verification</h3>
        <p className="muted">Loading your review queue…</p>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="action-card">
        <h3>Document Verification</h3>
        <p className="muted">No documents are awaiting your review yet.</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Document Verification</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {rows.map((row) => (
          <div className="card" key={row.id}>
            <span className="badge">{row.status}</span>
            <h4 style={{ marginTop: 10 }}>{row.document}</h4>
            <p className="muted" style={{ fontSize: 13 }}>{row.student}</p>
            <button className="btn small" disabled={busyId === row.id} onClick={() => view(row)}>
              {busyId === row.id ? "Preparing…" : "View document"}
            </button>
            {openId === row.id ? (
              <form className="form" onSubmit={(event) => submit(event, row.id)} style={{ marginTop: 8 }}>
                <div className="field">
                  <label htmlFor={`decision-${row.id}`}>Decision</label>
                  <select id={`decision-${row.id}`} name="verification_status" required>
                    <option value="verified">Verified</option>
                    <option value="rejected">Rejected</option>
                    <option value="changes_required">Changes required</option>
                  </select>
                </div>
                <div className="field">
                  <label htmlFor={`notes-${row.id}`}>Reviewer notes</label>
                  <textarea id={`notes-${row.id}`} name="notes" />
                </div>
                <button className="btn small" disabled={busyId === row.id}>
                  {busyId === row.id ? "Submitting…" : "Submit review"}
                </button>
              </form>
            ) : (
              <button className="btn small" style={{ marginLeft: 8 }} onClick={() => setOpenId(row.id)}>Review</button>
            )}
            {message?.id === row.id && (
              <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>
                {message.text}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

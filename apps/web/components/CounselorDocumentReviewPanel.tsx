"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type DocumentRow = { id: string; student: string; document: string; status: string; notes?: string | null };
export type ReviewDecision = "verified" | "rejected" | "changes_required";

const ALL_DECISIONS: ReviewDecision[] = ["verified", "rejected", "changes_required"];
const DECISION_LABELS: Record<ReviewDecision, string> = { verified: "Verified", rejected: "Rejected", changes_required: "Changes required" };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to complete this action.";
}

type Props = { queueUrl?: string; decisions?: ReviewDecision[]; pendingOnly?: boolean; emptyText?: string };

// OVS-005: a Counselor's assigned document queue with a real "View document" download action and Verify/Reject controls.
// AGN-003 (DEC-SCOPE-041 P5/P6): reused on the agent Documents page -- `pendingOnly` (agents decide pending documents only) and
// `decisions` (staff: verified only). Every prop defaults to the counselor panel exactly as before; a failed load now says so.
export default function CounselorDocumentReviewPanel({
  queueUrl = "/api/v1/portal/overseas/counselor/documents",
  decisions = ALL_DECISIONS,
  pendingOnly = false,
  emptyText = "No documents are awaiting your review yet.",
}: Props) {
  const router = useRouter();
  const [rows, setRows] = useState<DocumentRow[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  const load = useCallback(() => {
    fetch(queueUrl)
      .then((res) => {
        if (!res.ok) throw new Error(String(res.status));
        return res.json();
      })
      .then((data) => {
        setLoadFailed(false);
        setRows(data.rows || []);
      })
      .catch(() => {
        setLoadFailed(true);
        setRows([]);
      });
  }, [queueUrl]);

  useEffect(load, [load]);

  // After a review the queue reloads; keep keyboard users on the row's result instead of the top of the page.
  useEffect(() => {
    if (message) document.getElementById(`review-status-${message.id}`)?.focus();
  }, [message, rows]);

  function retry() {
    setRows(null);
    setLoadFailed(false);
    load();
  }

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

  if (loadFailed) {
    return (
      <div className="action-card">
        <h3>Document Verification</h3>
        <p className="form-error" role="alert">Couldn&apos;t load documents.</p>
        <div><button className="btn secondary small" onClick={retry}>Try again</button></div>
      </div>
    );
  }

  if (rows === null) {
    return (
      <div className="action-card">
        <h3>Document Verification</h3>
        <p className="muted" role="status">Loading your review queue…</p>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="action-card">
        <h3>Document Verification</h3>
        <p className="muted">{emptyText}</p>
      </div>
    );
  }

  const single = decisions.length === 1 ? decisions[0] : null;

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
                {single ? (
                  <input type="hidden" name="verification_status" value={single} />
                ) : (
                  <div className="field">
                    <label htmlFor={`decision-${row.id}`}>Decision</label>
                    <select id={`decision-${row.id}`} name="verification_status" required>
                      {decisions.map((value) => <option key={value} value={value}>{DECISION_LABELS[value]}</option>)}
                    </select>
                  </div>
                )}
                <div className="field">
                  <label htmlFor={`notes-${row.id}`}>Reviewer notes</label>
                  <textarea id={`notes-${row.id}`} name="notes" maxLength={10000} />
                </div>
                <button className="btn small" disabled={busyId === row.id}>
                  {busyId === row.id ? "Submitting…" : single ? `Mark ${DECISION_LABELS[single].toLowerCase()}` : "Submit review"}
                </button>
              </form>
            ) : (
              (!pendingOnly || row.status === "pending") && <button className="btn small" style={{ marginLeft: 8 }} onClick={() => setOpenId(row.id)}>Review</button>
            )}
            {message?.id === row.id && (
              <div id={`review-status-${row.id}`} tabIndex={-1} className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>
                {message.text}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

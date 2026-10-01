"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { detailMessage, sendJson } from "@/lib/apiErrors";

type DocumentRow = { id: string; student: string; document: string; status: string; notes?: string | null };
export type ReviewDecision = "verified" | "rejected" | "changes_required";

const ALL_DECISIONS: ReviewDecision[] = ["verified", "rejected", "changes_required"];
const DECISION_LABELS: Record<ReviewDecision, string> = { verified: "Verified", rejected: "Rejected", changes_required: "Changes required" };
// AGN-003 browser QA-04/QA-02: how a failed request reads. A 5xx carries nothing useful; a dropped connection on a button action
// (View document) has no typed entry to keep -- the review form's own drop message comes from sendJson (NOT_COMPLETED).
const SERVER_FAILED = "The server couldn't complete this. Please try again in a moment.";
const UNREACHABLE = "Couldn't reach the server. Check your connection and try again.";

// AGN-003 browser QA-05: a status reads as words ("Changes required"), never as the stored value.
function statusLabel(status: string): string {
  const label = DECISION_LABELS[status as ReviewDecision] ?? status.replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
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
  // AGN-003 browser QA-06: viewing and submitting are separate actions, so each shows (and blocks) only itself.
  const [viewingId, setViewingId] = useState<string | null>(null);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
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
    setViewingId(row.id);
    setMessage(null);
    let response: Response;
    try {
      response = await fetch(`/api/v1/workflows/overseas/documents/${row.id}/download`);
    } catch {
      // AGN-003 browser QA-02: a dropped connection must free the button and say so, not leave it on "Preparing…".
      setViewingId(null);
      setMessage({ id: row.id, text: UNREACHABLE, failed: true });
      return;
    }
    const data = await response.json().catch(() => ({}));
    setViewingId(null);
    if (!response.ok) {
      setMessage({ id: row.id, text: response.status >= 500 ? SERVER_FAILED : detailMessage(data.detail, "Unable to complete this action."), failed: true });
      return;
    }
    window.open(data.url, "_blank", "noreferrer");
  }

  async function submit(event: FormEvent<HTMLFormElement>, documentId: string) {
    event.preventDefault();
    setSubmittingId(documentId);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    // AGN-003 browser QA-01: sendJson never throws -- a dropped connection comes back as its "entry is kept" message.
    const outcome = await sendJson(`/api/v1/workflows/overseas/documents/${documentId}/verify`, "PATCH", {
      verification_status: String(form.get("verification_status")),
      notes: String(form.get("notes") || "") || null,
    });
    setSubmittingId(null);
    if (!outcome.ok) {
      setMessage({ id: documentId, text: outcome.status !== undefined && outcome.status >= 500 ? SERVER_FAILED : outcome.message, failed: true });
      // AGN-003 browser QA-03: someone else decided it first -- show the real status instead of a stale form.
      if (outcome.status === 409) {
        setOpenId(null);
        router.refresh();
        load();
      }
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
            <span className="badge">{statusLabel(row.status)}</span>
            <h4 style={{ marginTop: 10 }}>{row.document}</h4>
            <p className="muted" style={{ fontSize: 13 }}>{row.student}</p>
            {/* AGN-003 browser QA-08: the row's actions share one wrapping line instead of an offset second line. */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              <button className="btn small" disabled={viewingId === row.id} onClick={() => view(row)}>
                {viewingId === row.id ? "Preparing…" : "View document"}
              </button>
              {openId !== row.id && (!pendingOnly || row.status === "pending") && <button className="btn small" onClick={() => setOpenId(row.id)}>Review</button>}
            </div>
            {openId === row.id && (
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
                <button className="btn small" disabled={submittingId === row.id}>
                  {submittingId === row.id ? "Submitting…" : single ? `Mark ${DECISION_LABELS[single].toLowerCase()}` : "Submit review"}
                </button>
              </form>
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

"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { FILE_ACCEPT } from "@/lib/agentDocuments";
import { detailMessage, sendJson, sendRequest } from "@/lib/apiErrors";
import { documentStatusLabel, needsExpiry, reviewStatusesFor } from "@/lib/documentChecklists";
import { formatCalendarDate, formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";

// ccrm-021 (DEC-SCOPE-249 S5): reviewer, review date, expiry, and whether this row replaced an earlier version.
type DocumentRow = {
  id: string;
  student: string;
  document: string;
  status: string;
  notes?: string | null;
  reviewer?: string | null;
  reviewed_at?: string | null;
  expiry_date?: string | null;
  replaces_earlier?: boolean;
};

// AGN-003 browser QA-04/QA-02: how a failed request reads. A 5xx carries nothing useful; a dropped connection on a button action
// (View document) has no typed entry to keep -- the review form's own drop message comes from sendJson (NOT_COMPLETED).
const SERVER_FAILED = "The server couldn't complete this. Please try again in a moment.";
const UNREACHABLE = "Couldn't reach the server. Check your connection and try again.";

// AGN-003 browser QA-05: a status reads as words ("Re-upload required"), never as the stored value.
const statusLabel = documentStatusLabel;

type Props = { queueUrl?: string; decisions?: string[]; pendingOnly?: boolean; emptyText?: string };

// OVS-005: a Counselor's assigned document queue with a real "View document" download action and review controls.
// AGN-003 (DEC-SCOPE-044 P5/P6): `pendingOnly` (decide pending documents only) and `decisions` (a fixed list) narrow it. By default
// each row offers the ccrm-021 statuses for its type (Draft/Review/Approved on CV / SOP only), takes an expiry date (a passport needs
// one to be verified) and can be replaced with a new version (POST .../versions; the server archives the old one).
export default function CounselorDocumentReviewPanel({
  queueUrl = "/api/v1/portal/overseas/counselor/documents",
  decisions,
  pendingOnly = false,
  emptyText = "No documents are awaiting your review yet.",
}: Props) {
  const router = useRouter();
  const [rows, setRows] = useState<DocumentRow[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [replaceId, setReplaceId] = useState<string | null>(null);
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

  function failed(documentId: string, status: number | undefined, text: string) {
    setMessage({ id: documentId, text: status !== undefined && status >= 500 ? SERVER_FAILED : text, failed: true });
    // AGN-003 browser QA-03: someone else changed it first -- show the real status instead of a stale form.
    if (status === 409) closeAndReload();
  }

  async function submit(event: FormEvent<HTMLFormElement>, documentId: string) {
    event.preventDefault();
    setSubmittingId(documentId);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const expiry = String(form.get("expiry_date") || "");
    // AGN-003 browser QA-01: sendJson never throws -- a dropped connection comes back as its "entry is kept" message.
    const outcome = await sendJson(`/api/v1/workflows/overseas/documents/${documentId}/verify`, "PATCH", {
      verification_status: String(form.get("verification_status")),
      notes: String(form.get("notes") || "") || null,
      ...(expiry ? { expiry_date: expiry } : {}),
    });
    setSubmittingId(null);
    if (!outcome.ok) return failed(documentId, outcome.status, outcome.message);
    setMessage({ id: documentId, text: "Document reviewed -- the student has been notified.", failed: false });
    closeAndReload();
  }

  async function replace(event: FormEvent<HTMLFormElement>, documentId: string) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (!form.get("expiry_date")) form.delete("expiry_date");
    setSubmittingId(documentId);
    setMessage(null);
    const outcome = await sendRequest(`/api/v1/workflows/overseas/documents/${documentId}/versions`, { method: "POST", body: form });
    setSubmittingId(null);
    if (!outcome.ok) return failed(documentId, outcome.status, outcome.message);
    // The new version has its own id, so the confirmation shows on its row once the queue reloads.
    setMessage({ id: String(outcome.data.id), text: "New version uploaded -- waiting for review. The previous file is kept in its history.", failed: false });
    closeAndReload();
  }

  // The document's status changed (our review, or someone else's): close the form and show the queue as the server has it now.
  function closeAndReload() {
    setOpenId(null);
    setReplaceId(null);
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

  return (
    <div className="action-card">
      <h3>Document Verification</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {rows.map((row) => {
          const options = decisions ?? reviewStatusesFor(row.document);
          const single = options.length === 1 ? options[0] : null;
          const name = `${row.document} for ${row.student}`;
          const reviewed = [
            row.reviewed_at && `Reviewed${row.reviewer ? ` by ${row.reviewer}` : ""} ${formatDateTimeIn(row.reviewed_at, viewerTimeZone())}`,
            row.expiry_date && `Expires ${formatCalendarDate(row.expiry_date)}`,
            row.replaces_earlier && "Replaces an earlier version",
          ]
            .filter(Boolean)
            .join(" · ");
          return (
            <div className="card" key={row.id}>
              <span className="badge">{statusLabel(row.status)}</span>
              <h4 style={{ marginTop: 10 }}>{row.document}</h4>
              <p className="muted" style={{ fontSize: 13 }}>{row.student}</p>
              {row.notes && <p className="muted" style={{ fontSize: 13 }}>Notes: {row.notes}</p>}
              {reviewed && <p className="muted" style={{ fontSize: 13 }}>{reviewed}</p>}
              {/* AGN-003 browser QA-08: the row's actions share one wrapping line instead of an offset second line. */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                <button className="btn small" disabled={viewingId === row.id} onClick={() => view(row)}>
                  {viewingId === row.id ? "Preparing…" : "View document"}
                </button>
                {openId !== row.id && (!pendingOnly || row.status === "pending") && (
                  <button className="btn small" onClick={() => { setReplaceId(null); setOpenId(row.id); }}>Review</button>
                )}
                {!pendingOnly && replaceId !== row.id && (
                  <button className="btn secondary small" aria-label={`Replace file of ${name}`} onClick={() => { setOpenId(null); setReplaceId(row.id); }}>
                    Replace file
                  </button>
                )}
              </div>
              {openId === row.id && (
                <form className="form" onSubmit={(event) => submit(event, row.id)} style={{ marginTop: 8 }}>
                  {single ? (
                    <input type="hidden" name="verification_status" value={single} />
                  ) : (
                    <>
                      <div className="field">
                        <label htmlFor={`decision-${row.id}`}>Decision</label>
                        <select id={`decision-${row.id}`} name="verification_status" required>
                          {options.map((value) => <option key={value} value={value}>{statusLabel(value)}</option>)}
                        </select>
                      </div>
                      <div className="field">
                        <label htmlFor={`expiry-${row.id}`}>{needsExpiry(row.document) ? "Expiry date (needed to verify a passport)" : "Expiry date (optional)"}</label>
                        <input id={`expiry-${row.id}`} name="expiry_date" type="date" defaultValue={row.expiry_date ?? ""} />
                      </div>
                    </>
                  )}
                  <div className="field">
                    <label htmlFor={`notes-${row.id}`}>Reviewer notes</label>
                    <textarea id={`notes-${row.id}`} name="notes" maxLength={10000} />
                  </div>
                  <button className="btn small" disabled={submittingId === row.id}>
                    {submittingId === row.id ? "Submitting…" : single ? `Mark ${statusLabel(single).toLowerCase()}` : "Submit review"}
                  </button>
                </form>
              )}
              {replaceId === row.id && (
                <form className="form" aria-label={`Replace file of ${name}`} onSubmit={(event) => replace(event, row.id)} style={{ marginTop: 8 }}>
                  <div className="field">
                    <label htmlFor={`replace-${row.id}`}>New file (PDF, JPEG or PNG)</label>
                    <input id={`replace-${row.id}`} name="file" type="file" accept={FILE_ACCEPT} required />
                  </div>
                  <div className="field">
                    <label htmlFor={`replace-expiry-${row.id}`}>Expiry date (optional; empty keeps the current one)</label>
                    <input id={`replace-expiry-${row.id}`} name="expiry_date" type="date" />
                  </div>
                  <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                    The new file starts at Pending review. The previous file stays in the document&apos;s history.
                  </p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    <button className="btn small" disabled={submittingId === row.id}>{submittingId === row.id ? "Uploading…" : "Upload new version"}</button>
                    <button type="button" className="btn secondary small" onClick={() => setReplaceId(null)}>Cancel</button>
                  </div>
                </form>
              )}
              {message?.id === row.id && (
                <div id={`review-status-${row.id}`} tabIndex={-1} className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>
                  {message.text}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

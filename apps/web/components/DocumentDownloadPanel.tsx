"use client";

import { useEffect, useState } from "react";

type DocumentRow = { id: string; type: string; status: string; notes: string | null };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to fetch the download link.";
}

// OVS-005 security note (OVS-DOC-02): the generic table above used to surface the raw,
// permanently-public `file_url` as plain text -- same class of gap already fixed for
// STU-007's certificates. This exchanges a document's id for a real download URL via
// GET .../documents/{id}/download, verified server-side as belonging to the requesting
// student, rather than trusting the stored value directly.
export default function DocumentDownloadPanel() {
  const [rows, setRows] = useState<DocumentRow[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/portal/overseas/student/documents")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => !cancelled && setRows(data.rows || []))
      .catch(() => !cancelled && setRows([]));
    return () => {
      cancelled = true;
    };
  }, []);

  async function download(row: DocumentRow) {
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

  if (rows === null) {
    return (
      <div className="action-card">
        <h3>Your Documents</h3>
        <p className="muted">Loading your documents…</p>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="action-card">
        <h3>Your Documents</h3>
        <p className="muted">Upload a document above to see it listed here.</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Your Documents</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {rows.map((row) => (
          <div className="card" key={row.id}>
            <span className="badge">{row.status}</span>
            <h4 style={{ marginTop: 10 }}>{row.type}</h4>
            {row.notes && <p className="muted" style={{ fontSize: 13 }}>{row.notes}</p>}
            <button className="btn small" disabled={busyId === row.id} onClick={() => download(row)}>
              {busyId === row.id ? "Preparing…" : "Download"}
            </button>
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

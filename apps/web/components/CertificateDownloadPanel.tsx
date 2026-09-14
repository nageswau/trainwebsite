"use client";

import { useEffect, useState } from "react";

type CertificateRow = { id: string; number: string; program: string; issued: string; status: string; verification: string };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to fetch the download link.";
}

// STU-007: "Student downloads certificate once eligibility criteria are met." The table
// above lists issued certificates but (like every generic portal table) only ever
// renders plain text, never a working link -- and the raw `file_url` it used to show
// was a permanently-public object path anyway, not the "signed, short-lived URL" this
// feature's own contract calls for. This exchanges a certificate's id for a real,
// short-lived download URL via GET .../certificates/{id}/download, verified server-side
// as belonging to the requesting student, and opens it. STU-007-AC02 ("certificate
// unavailable before eligibility met") holds by construction -- no `Certificate` row
// exists until a trainer/admin issues one, so an ineligible student simply sees none yet.
export default function CertificateDownloadPanel() {
  const [rows, setRows] = useState<CertificateRow[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/portal/it/student/certificates")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => !cancelled && setRows(data.rows || []))
      .catch(() => !cancelled && setRows([]));
    return () => {
      cancelled = true;
    };
  }, []);

  async function download(row: CertificateRow) {
    setBusyId(row.id);
    setMessage(null);
    const response = await fetch(`/api/v1/workflows/it/certificates/${row.id}/download`);
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
        <h3>Certificates</h3>
        <p className="muted">Loading your certificates…</p>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="action-card">
        <h3>Certificates</h3>
        <p className="muted">No certificate has been issued yet. It becomes available here once your course completion criteria are met.</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Certificates</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {rows.map((row) => (
          <div className="card" key={row.id}>
            <span className="badge">{row.status}</span>
            <h4 style={{ marginTop: 10 }}>{row.program}</h4>
            <p className="muted" style={{ fontSize: 13 }}>{row.number}</p>
            <button className="btn small" disabled={busyId === row.id} onClick={() => download(row)}>
              {busyId === row.id ? "Preparing…" : "Download certificate"}
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

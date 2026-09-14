"use client";

import { useState } from "react";

// ADM-014-AC02: exporting the security/audit log is itself a cross-division privileged
// action -- `POST /admin/audit/export` is Super-Admin-only and self-audit-logs the
// export in the same transaction as the write. No such action existed anywhere before
// this feature (only the read-only /admin/audit view did).
export default function AuditExportPanel() {
  const [busy, setBusy] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [rowCount, setRowCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    setDownloadUrl(null);
    try {
      const response = await fetch("/api/v1/admin/audit/export", { method: "POST" });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        setError(data?.message || "Could not export the audit log. Please try again.");
        return;
      }
      setDownloadUrl(data.url);
      setRowCount(data.row_count);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="action-card">
      <h3>Export audit log</h3>
      <p className="muted">Downloads the most recent audit records across both divisions -- this export action is itself audit-logged.</p>
      <button className="btn" disabled={busy} onClick={() => void submit()}>
        {busy ? "Preparing export…" : "Export audit log"}
      </button>
      {error && <p role="alert" className="error">{error}</p>}
      {downloadUrl && (
        <p role="status">
          Export ready ({rowCount} record{rowCount === 1 ? "" : "s"}). <a href={downloadUrl} target="_blank" rel="noreferrer">Download it here</a>.
        </p>
      )}
    </div>
  );
}

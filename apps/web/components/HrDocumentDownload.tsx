"use client";

import { useState } from "react";

const FAILED = "Couldn't open the document. Please try again.";

// nehn-017 (DEC-SCOPE-310): one allowed-type document of a student, opened through the audited HR route, which hands back a short-lived
// URL (nehn-003). The button is busy while the request runs so a double click sends one request; a refusal is shown beside it.
export default function HrDocumentDownload({ studentId, documentId, name }: { studentId: string; documentId: string; name: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function open() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/v1/hr/students/${studentId}/documents/${documentId}/download`, { cache: "no-store" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || typeof data.url !== "string") setError(typeof data.detail === "string" ? data.detail : FAILED);
      else window.open(data.url, "_blank", "noreferrer");
    } catch {
      setError(FAILED);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span style={{ display: "inline-flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
      <button type="button" className="btn small secondary" onClick={open} disabled={busy} aria-busy={busy} aria-label={`Download ${name}`}>
        {busy ? "Opening…" : "Download"}
      </button>
      {error && <span className="form-error" role="alert">{error}</span>}
    </span>
  );
}

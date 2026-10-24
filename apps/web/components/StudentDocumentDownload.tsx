"use client";

import { useState } from "react";

import { sendRequest } from "@/lib/apiErrors";

// ccrm-009 (DEC-SCOPE-252): one document's download on the student 360. The id is exchanged for a short-lived link by the existing,
// scoped and audited route (OVS-005); the button is only rendered where that route allows the reader (`can_download`).
export default function StudentDocumentDownload({ id, name }: { id: string; name: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    if (busy) return;
    setBusy(true);
    setError(null);
    const outcome = await sendRequest(`/api/v1/workflows/overseas/documents/${encodeURIComponent(id)}/download`, { method: "GET" });
    setBusy(false);
    if (!outcome.ok || typeof outcome.data.url !== "string") {
      setError(outcome.ok ? "The download link could not be created." : outcome.message);
      return;
    }
    window.open(outcome.data.url, "_blank", "noopener");
  }

  return (
    <span style={{ display: "inline-grid", gap: 4 }}>
      <button type="button" className="btn small secondary" aria-busy={busy} aria-label={`Download ${name}`} onClick={download}>
        {busy ? "Preparing…" : "Download"}
      </button>
      <span role="status" aria-live="polite" className={error ? "form-error" : undefined}>{error}</span>
    </span>
  );
}

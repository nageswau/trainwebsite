"use client";

import { useState } from "react";

type RequestResult = {
  id: string;
  type: "export" | "delete";
  status: string;
  rejection_reason: string | null;
};

// SEC-002: self-service GDPR export/delete, `POST /account/data-requests`
// (API_CONTRACT.md #11). AC02: a failed/blocked deletion is never a silent failure --
// the rejection reason (e.g. an active retention hold) is always shown, not swallowed.
export default function DataPrivacyPanel() {
  const [busy, setBusy] = useState<"export" | "delete" | null>(null);
  const [result, setResult] = useState<RequestResult | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(type: "export" | "delete") {
    setBusy(type);
    setError(null);
    setResult(null);
    setDownloadUrl(null);
    try {
      const response = await fetch("/api/v1/account/data-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ type }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        setError(data?.message || "Could not submit your request. Please try again.");
        return;
      }
      setResult(data);
      if (type === "export" && data.status === "fulfilled") {
        const download = await fetch(`/api/v1/account/data-requests/${data.id}/export`);
        const downloadData = await download.json().catch(() => null);
        if (download.ok) setDownloadUrl(downloadData.url);
      }
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="action-card">
      <h3>Your data, your control</h3>
      <p className="muted">Request a copy of your account data, or ask us to delete your account.</p>
      <div className="field" style={{ flexDirection: "row", gap: 12 }}>
        <button className="btn" disabled={busy !== null} onClick={() => void submit("export")}>
          {busy === "export" ? "Preparing your export…" : "Request a copy of my data"}
        </button>
        <button className="btn secondary" disabled={busy !== null} onClick={() => void submit("delete")}>
          {busy === "delete" ? "Submitting…" : "Request account deletion"}
        </button>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      {result?.type === "export" && result.status === "fulfilled" && downloadUrl && (
        <p role="status">Your export is ready. <a href={downloadUrl} target="_blank" rel="noreferrer">Download it here</a>.</p>
      )}
      {result?.type === "delete" && result.status === "rejected" && (
        <p role="alert">We can&apos;t delete your account yet: {result.rejection_reason}</p>
      )}
      {result?.type === "delete" && result.status === "in_progress" && (
        <p role="status">Your deletion request has been received and is awaiting review by an administrator.</p>
      )}
    </div>
  );
}

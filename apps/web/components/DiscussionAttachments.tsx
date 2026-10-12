"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { sendRequest } from "@/lib/apiErrors";
import { DISCUSSIONS_API, type DiscussionDetail } from "@/lib/managementDiscussions";

const TYPES = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png";
const MAX = 10;

// mgmt-027 (MD10): a discussion's attachments. Each is shared with the responsible person or not (not by default); removing one asks
// first. Buttons are disabled while a request runs (no double submit); the page refreshes after each change.
export default function DiscussionAttachments({ discussion }: { discussion: DiscussionDetail }) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [shareable, setShareable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [result, setResult] = useState<{ text: string; failed: boolean } | null>(null);
  const [inputKey, setInputKey] = useState(0);
  const base = `${DISCUSSIONS_API}/${discussion.id}/attachments`;
  const full = discussion.attachments.length >= MAX;

  async function upload() {
    if (!file) {
      setResult({ text: "Choose a PDF, JPEG or PNG file first.", failed: true });
      return;
    }
    const form = new FormData();
    form.append("file", file);
    form.append("shareable", String(shareable));
    setBusy(true);
    setResult(null);
    const outcome = await sendRequest(base, { method: "POST", body: form });
    setBusy(false);
    if (!outcome.ok) {
      setResult({ text: outcome.message, failed: true });
      return;
    }
    setFile(null);
    setShareable(false);
    setInputKey((k) => k + 1);
    setResult({ text: "File attached.", failed: false });
    router.refresh();
  }

  async function remove(id: string) {
    setBusy(true);
    setResult(null);
    const outcome = await sendRequest(`${base}/${id}`, { method: "DELETE" });
    setBusy(false);
    setRemoving(null);
    setResult(outcome.ok ? { text: "File removed.", failed: false } : { text: outcome.message, failed: true });
    if (outcome.ok) router.refresh();
  }

  return (
    <section aria-labelledby="discussion-attachments" className="action-card" style={{ display: "grid", gap: 12 }}>
      <h3 id="discussion-attachments" style={{ margin: 0 }}>Attachments</h3>
      {discussion.attachments.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No attachments yet.</p>
      ) : (
        <ul style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 8 }}>
          {discussion.attachments.map((a) => {
            const label = a.name ?? "Attachment";
            return (
              <li key={a.id} style={{ overflowWrap: "anywhere" }}>
                <a className="kpi-link" href={`${base}/${a.id}`}>{label}</a>
                <span className="muted" style={{ fontSize: 13 }}> · {a.shareable ? "Shared with the responsible person" : "Management only"}</span>
                {removing === a.id ? (
                  <span className="actions" style={{ display: "inline-flex", marginLeft: 8 }}>
                    <button className="btn small" type="button" disabled={busy} onClick={() => void remove(a.id)}>Confirm removal</button>
                    <button className="btn ghost small" type="button" disabled={busy} onClick={() => setRemoving(null)}>Keep it</button>
                  </span>
                ) : (
                  <button className="btn ghost small" type="button" disabled={busy} aria-label={`Remove ${label}`} style={{ marginLeft: 8 }} onClick={() => setRemoving(a.id)}>Remove</button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {full ? (
        <p className="muted" style={{ margin: 0 }}>This discussion has the maximum of {MAX} attachments. Remove one to add another.</p>
      ) : (
        <div className="form-grid" style={{ alignItems: "end" }}>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="discussion-file">Add a file</label>
            <input key={inputKey} id="discussion-file" type="file" accept={TYPES} disabled={busy} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <span className="muted" style={{ fontSize: 13 }}>PDF, JPEG or PNG.</span>
          </div>
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" style={{ width: "auto" }} checked={shareable} disabled={busy} onChange={(e) => setShareable(e.target.checked)} />
            Share with the responsible person
          </label>
          <div className="actions">
            <button className="btn secondary" type="button" disabled={busy} onClick={() => void upload()}>{busy ? "Working…" : "Upload"}</button>
          </div>
        </div>
      )}
      {result && <p className={result.failed ? "form-error" : "form-message"} role={result.failed ? "alert" : "status"}>{result.text}</p>}
    </section>
  );
}

"use client";

import { FormEvent, useState } from "react";
import AgentDocumentHistory from "./AgentDocumentHistory";
import AgentDocumentReviewForm from "./AgentDocumentReviewForm";
import { detailMessage, sendRequest } from "@/lib/apiErrors";
import { AgentDocumentItem, documentName, DOCUMENTS_URL, downloadUrl, FILE_ACCEPT, formatSize, reviewDecisions, statusLabel } from "@/lib/agentDocuments";
import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";
import type { User } from "@/lib/types";

type Panel = "review" | "replace" | "history" | null;
type Note = { text: string; failed: boolean } | null; // this card's own errors
const STATUS_CLASS: Record<string, string> = { pending: "status pending", verified: "status", rejected: "status error", changes_required: "status error" };

// AGN-009: one document and its actions. Download uses the scoped OVS-005 route (the link is fetched on demand and never stored);
// review follows the §6 matrix; replace is offered only where the server allows it (`replaceable`). After any change the list
// reloads (`onChanged`) and shows the success message itself, because the document may leave the Pending view; errors stay here.
export default function AgentDocumentCard({ doc, user, onChanged }: { doc: AgentDocumentItem; user: User; onChanged: (message?: string) => void }) {
  const [panel, setPanel] = useState<Panel>(null);
  const [note, setNote] = useState<Note>(null);
  const [busy, setBusy] = useState<"download" | "replace" | null>(null);
  const name = `${documentName(doc)} for ${doc.student}`;
  const decisions = doc.verification_status === "pending" ? reviewDecisions(user) : [];
  const toggle = (next: Panel) => setPanel((current) => (current === next ? null : next));

  async function download() {
    setBusy("download");
    setNote(null);
    try {
      const response = await fetch(downloadUrl(doc.id));
      const data = await response.json().catch(() => ({}));
      if (!response.ok || typeof data.url !== "string") return setNote({ text: detailMessage(data.detail, "The document could not be opened."), failed: true });
      window.open(data.url, "_blank", "noreferrer");
    } catch {
      setNote({ text: "Couldn't reach the server. Check your connection and try again.", failed: true });
    } finally {
      setBusy(null);
    }
  }

  async function replace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const file = form.get("file");
    if (!(file instanceof File) || !file.size) return;
    setBusy("replace");
    const outcome = await sendRequest(`${DOCUMENTS_URL}/${doc.id}/file`, { method: "PUT", body: form });
    setBusy(null);
    if (!outcome.ok) {
      setNote({ text: outcome.message, failed: true });
      if (outcome.status === 409) onChanged();
      return;
    }
    setPanel(null);
    onChanged(`${name}: new file uploaded, waiting for review.`);
  }

  function reviewed(text: string, failed: boolean, status?: number) {
    if (failed) setNote({ text, failed });
    if (!failed || status === 409) {
      setPanel(null);
      onChanged(failed ? undefined : text);
    }
  }

  const details = [doc.university && `Application: ${doc.university}`, doc.uploaded_by && `Uploaded by ${doc.uploaded_by}`, formatDateTimeIn(doc.created_at, viewerTimeZone()), formatSize(doc.file_size)].filter(Boolean).join(" · ");
  return (
    <li className="card" style={{ padding: 16 }}>
      <strong>{doc.student}</strong>
      {!doc.has_login && <span className="badge" style={{ marginLeft: 8 }}>no login</span>}
      <div>
        {documentName(doc)} <span className={STATUS_CLASS[doc.verification_status] ?? "status"}>{statusLabel(doc.verification_status)}</span>
      </div>
      {doc.reviewer_notes && <div className="muted">Reason: {doc.reviewer_notes}</div>}
      <div className="muted">{details}</div>
      <div className="actions" style={{ marginTop: 8 }}>
        <button type="button" className="btn secondary small" aria-label={`Download ${name}`} disabled={busy === "download"} onClick={download}>
          {busy === "download" ? "Preparing…" : "Download"}
        </button>
        {decisions.length > 0 && (
          <button type="button" className="btn secondary small" aria-label={`Review ${name}`} aria-expanded={panel === "review"} onClick={() => toggle("review")}>
            Review
          </button>
        )}
        {doc.replaceable && (
          <button type="button" className="btn secondary small" aria-label={`Replace file of ${name}`} aria-expanded={panel === "replace"} onClick={() => toggle("replace")}>
            Replace file
          </button>
        )}
        <button type="button" className="btn secondary small" aria-label={`History of ${name}`} aria-expanded={panel === "history"} onClick={() => toggle("history")}>
          History
        </button>
      </div>
      {note && (
        <p className={note.failed ? "form-error" : "form-message"} role={note.failed ? "alert" : "status"} style={{ marginTop: 8 }}>
          {note.text}
        </p>
      )}
      {panel === "review" && <AgentDocumentReviewForm id={doc.id} name={name} decisions={decisions} onDone={reviewed} />}
      {panel === "replace" && (
        <form className="form" aria-label={`Replace file of ${name}`} onSubmit={replace} style={{ marginTop: 12 }}>
          <div className="field">
            <label htmlFor={`replace-${doc.id}`}>New file (PDF, JPEG or PNG)</label>
            <input id={`replace-${doc.id}`} name="file" type="file" accept={FILE_ACCEPT} required />
          </div>
          <p className="muted" style={{ margin: 0 }}>
            The document goes back to Pending review. The previous file stays in its history.
          </p>
          <div className="actions">
            <button className="btn small" disabled={busy === "replace"}>
              {busy === "replace" ? "Uploading…" : "Upload new file"}
            </button>
          </div>
        </form>
      )}
      {panel === "history" && <AgentDocumentHistory id={doc.id} name={name} />}
    </li>
  );
}

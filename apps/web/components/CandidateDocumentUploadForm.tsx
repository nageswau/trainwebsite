"use client";

import { type FormEvent, useRef, useState } from "react";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { sendRequest } from "@/lib/apiErrors";
import { DOCUMENT_ACCEPT, DOCUMENT_MAX_BYTES, DOCUMENT_TYPES, type DocumentRequest, type DocumentType, documentTypeLabel } from "@/lib/candidateDocuments";

// hrc-015 (DEC-SCOPE-379 D6/D7): one document upload -- staff on the candidate page, or the candidate in the student portal. Choosing a
// pending request sets its type (the API requires them to match). PDF, DOC, DOCX, PNG or JPEG up to 5 MB; the API judges the bytes.
type Props = { url: string; idPrefix: string; requests: DocumentRequest[]; onUploaded: () => void };

export default function CandidateDocumentUploadForm({ url, idPrefix, requests, onUploaded }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const sending = useRef(false);
  const [documentType, setDocumentType] = useState<DocumentType>("certificate");
  const [title, setTitle] = useState("");
  const [requestId, setRequestId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const pending = requests.filter((r) => r.status === "pending");
  const id = (name: string) => `${idPrefix}-${name}`;

  function chooseRequest(value: string) {
    setRequestId(value);
    const request = pending.find((r) => r.id === value);
    if (request) setDocumentType(request.document_type);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const file = input.current?.files?.[0];
    if (!file) return setMessage({ text: "Choose a file first.", failed: true });
    if (file.size > DOCUMENT_MAX_BYTES) return setMessage({ text: "The document must be at most 5 MB.", failed: true });
    if (documentType === "other" && !title.trim()) return setMessage({ text: "Give the document a title.", failed: true });
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setMessage(null);
    const form = new FormData();
    form.append("document_type", documentType);
    if (title.trim()) form.append("title", title.trim());
    if (requestId) form.append("request_id", requestId);
    form.append("file", file);
    const outcome = await sendRequest(url, { method: "POST", body: form });
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: outcome.message, failed: true });
    if (input.current) input.current.value = "";
    setTitle("");
    setRequestId("");
    setMessage({ text: "Document uploaded.", failed: false });
    onUploaded();
  }

  return (
    <form onSubmit={submit} noValidate style={{ display: "grid", gap: 8 }} aria-label="Upload a document">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        {pending.length > 0 && (
          <div className="field" style={{ flex: "1 1 12rem", marginBottom: 0 }}>
            <label htmlFor={id("request")}>Fulfils request (optional)</label>
            <select id={id("request")} value={requestId} disabled={busy} onChange={(e) => chooseRequest(e.target.value)}>
              <option value="">No request</option>
              {pending.map((r) => <option key={r.id} value={r.id}>{documentTypeLabel(r.document_type)}</option>)}
            </select>
          </div>
        )}
        <div className="field" style={{ flex: "1 1 12rem", marginBottom: 0 }}>
          <label htmlFor={id("type")}>Document type</label>
          <select id={id("type")} value={documentType} disabled={busy || Boolean(requestId)} onChange={(e) => setDocumentType(e.target.value as DocumentType)}>
            {DOCUMENT_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>
        <div className="field" style={{ flex: "1 1 12rem", marginBottom: 0 }}>
          <label htmlFor={id("title")}>Title{documentType === "other" ? "" : " (optional)"}</label>
          <input id={id("title")} value={title} maxLength={120} disabled={busy} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div className="field" style={{ flex: "1 1 16rem", marginBottom: 0 }}>
          <label htmlFor={id("file")}>File</label>
          <span id={id("file-hint")} className="muted" style={{ fontSize: 13 }}>PDF, DOC, DOCX, PNG or JPEG, up to 5 MB</span>
          <input id={id("file")} ref={input} type="file" accept={DOCUMENT_ACCEPT} aria-describedby={id("file-hint")} disabled={busy} />
        </div>
        <button type="submit" className="btn secondary small" disabled={busy}>{busy ? "Uploading…" : "Upload document"}</button>
      </div>
      {message && <FormMessage message={message} style={{ fontSize: 13 }} />}
    </form>
  );
}

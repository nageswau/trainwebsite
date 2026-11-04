"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import CandidateDocumentUploadForm from "@/components/CandidateDocumentUploadForm";
import DocumentFileActions from "@/components/DocumentFileActions";
import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import LocalTime from "@/components/LocalTime";
import { sendRequest } from "@/lib/apiErrors";
import {
  type CandidateDocument, DOCUMENT_TYPES, type DocumentRequest, type DocumentsState, type DocumentType, REQUEST_STATUS_LABELS, documentTypeLabel,
} from "@/lib/candidateDocuments";
import { candidateUrl, fileSize } from "@/lib/recruiterCandidates";

// hrc-015 (DEC-SCOPE-379 D6/D7): a candidate's documents on the recruiter page -- requests (pending, then received or cancelled) and
// uploaded documents with Preview/Download. Readers (hr_team) see both; writers also request, cancel and upload. Every write reloads the
// list, so the request's status always comes from the server.
type Props = { candidateId: string; canEdit: boolean };

export const documentName = (d: CandidateDocument) => d.title || documentTypeLabel(d.document_type);
const uploaderName = (d: CandidateDocument) => (typeof d.uploaded_by === "object" && d.uploaded_by ? d.uploaded_by.full_name : null);

export default function RecruiterCandidateDocuments({ candidateId, canEdit }: Props) {
  const url = candidateUrl(candidateId, "/documents");
  const [state, setState] = useState<DocumentsState | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const load = useCallback(() => {
    setLoadFailed(false);
    fetch(url, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status));
        setState(await response.json());
      })
      .catch(() => setLoadFailed(true));
  }, [url]);
  useEffect(load, [load]);

  return (
    <section aria-labelledby="cand-docs-heading" className="action-card" style={{ display: "grid", gap: 12 }}>
      <h3 id="cand-docs-heading" style={{ margin: 0 }}>Documents</h3>
      {loadFailed ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>
          Couldn&apos;t load the documents. <button type="button" className="btn secondary small" onClick={load}>Try again</button>
        </p>
      ) : !state ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading documents…</p>
      ) : (
        <>
          <Requests candidateId={candidateId} requests={state.requests} canEdit={canEdit} onChanged={load} />
          <h4 style={{ margin: 0 }}>Uploaded documents</h4>
          {state.documents.length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>No documents uploaded yet.</p>
          ) : (
            <ul aria-label="Uploaded documents" style={{ margin: 0, paddingLeft: 0, listStyle: "none", display: "grid", gap: 8 }}>
              {state.documents.map((d) => (
                <li key={d.id} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
                  <span style={{ fontWeight: 600, overflowWrap: "anywhere" }}>
                    {d.title ? `${documentTypeLabel(d.document_type)} — ${d.title}` : documentTypeLabel(d.document_type)}
                  </span>
                  {d.request_id && <span className="badge">Requested</span>}
                  <span className="muted" style={{ fontSize: 13, overflowWrap: "anywhere" }}>
                    {d.file_name ? `${d.file_name} · ` : ""}{fileSize(d.size_bytes)} · <LocalTime value={d.created_at} time />
                    {uploaderName(d) ? ` · ${uploaderName(d)}` : ""}
                  </span>
                  <DocumentFileActions linkUrl={`${url}/${encodeURIComponent(d.id)}/link`} contentType={d.content_type} label={documentName(d)} />
                </li>
              ))}
            </ul>
          )}
          {canEdit && <CandidateDocumentUploadForm url={url} idPrefix="cand-doc" requests={state.requests} onUploaded={load} />}
        </>
      )}
    </section>
  );
}

function Requests({ candidateId, requests, canEdit, onChanged }: { candidateId: string; requests: DocumentRequest[]; canEdit: boolean; onChanged: () => void }) {
  const base = candidateUrl(candidateId, "/document-requests");
  const sending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [documentType, setDocumentType] = useState<DocumentType>("certificate");
  const [note, setNote] = useState("");
  const [due, setDue] = useState("");
  const [message, setMessage] = useState<FormMessageState | null>(null);

  async function send(path: string, init: RequestInit, done: string) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setMessage(null);
    const outcome = await sendRequest(path, init);
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: outcome.message, failed: true });
    setMessage({ text: done, failed: false });
    return true;
  }

  async function request(event: FormEvent) {
    event.preventDefault();
    const body = { document_type: documentType, note: note.trim() || null, due_date: due || null };
    const sent = await send(base, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, "Document requested.");
    if (!sent) return;
    setNote("");
    setDue("");
    onChanged();
  }

  async function cancel(r: DocumentRequest) {
    if (await send(`${base}/${encodeURIComponent(r.id)}/cancel`, { method: "POST" }, "Request cancelled.")) onChanged();
  }

  return (
    <>
      <h4 style={{ margin: 0 }}>Requested documents</h4>
      {requests.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No documents requested yet.</p>
      ) : (
        <ul aria-label="Requested documents" style={{ margin: 0, paddingLeft: 0, listStyle: "none", display: "grid", gap: 8 }}>
          {requests.map((r) => (
            <li key={r.id} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
              <span style={{ fontWeight: 600 }}>{documentTypeLabel(r.document_type)}</span>
              <span className="badge">{REQUEST_STATUS_LABELS[r.status]}</span>
              {r.note && <span style={{ overflowWrap: "anywhere" }}>{r.note}</span>}
              <span className="muted" style={{ fontSize: 13 }}>
                Requested <LocalTime value={r.created_at} />{r.requested_by ? ` by ${r.requested_by.full_name}` : ""}
                {r.due_date ? ` · due ${r.due_date}` : ""}
                {r.received_at ? <> · received <LocalTime value={r.received_at} /></> : null}
              </span>
              {canEdit && r.status === "pending" && (
                <button type="button" className="btn secondary small" disabled={busy} aria-label={`Cancel request for ${documentTypeLabel(r.document_type)}`} onClick={() => void cancel(r)}>
                  Cancel request
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <form onSubmit={request} noValidate aria-label="Request a document" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
          <div className="field" style={{ flex: "1 1 12rem", marginBottom: 0 }}>
            <label htmlFor="cand-req-type">Document to request</label>
            <select id="cand-req-type" value={documentType} disabled={busy} onChange={(e) => setDocumentType(e.target.value as DocumentType)}>
              {DOCUMENT_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div className="field" style={{ flex: "2 1 16rem", marginBottom: 0 }}>
            <label htmlFor="cand-req-note">Note for the candidate (optional)</label>
            <input id="cand-req-note" value={note} maxLength={500} disabled={busy} onChange={(e) => setNote(e.target.value)} />
          </div>
          <div className="field" style={{ flex: "0 1 10rem", marginBottom: 0 }}>
            <label htmlFor="cand-req-due">Due date (optional)</label>
            <input id="cand-req-due" type="date" value={due} disabled={busy} onChange={(e) => setDue(e.target.value)} />
          </div>
          <button type="submit" className="btn secondary small" disabled={busy}>{busy ? "Sending…" : "Request document"}</button>
        </form>
      )}
      {message && <FormMessage message={message} style={{ fontSize: 13 }} />}
    </>
  );
}

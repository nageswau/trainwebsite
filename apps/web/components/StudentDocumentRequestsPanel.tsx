"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { FILE_ACCEPT } from "@/lib/agentDocuments";
import { sendRequest } from "@/lib/apiErrors";
import { DocumentRequest, MY_REQUESTS_URL, RequestPage, uploadUrl } from "@/lib/documentRequests";
import { formatCalendarDate } from "@/lib/formatDate";

type Message = { text: string; failed: boolean };

// ccrm-020 (DEC-SCOPE-266): an overseas student's "Requested documents" -- what the counselor asked for, by when, the counselor's note,
// and an upload against each (PDF, JPEG or PNG; the server checks the bytes). A rejected upload brings the request back here (R1).
export default function StudentDocumentRequestsPanel() {
  const router = useRouter();
  const [items, setItems] = useState<DocumentRequest[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const inFlight = useRef(false);

  const load = useCallback(async () => {
    setLoadError(null);
    const outcome = await sendRequest(MY_REQUESTS_URL, {});
    if (!outcome.ok) return setLoadError(outcome.message);
    setItems((outcome.data as unknown as RequestPage).items ?? []);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function upload(request: DocumentRequest, file: File | null, expiry: string) {
    if (inFlight.current) return;
    if (!file || !file.size) return setMessage({ text: `Choose a file for ${request.name}.`, failed: true });
    const body = new FormData();
    body.set("file", file);
    if (expiry) body.set("expiry_date", expiry);
    inFlight.current = true;
    setBusyId(request.id);
    setMessage(null);
    const outcome = await sendRequest(uploadUrl(request.id), { method: "POST", body });
    inFlight.current = false;
    setBusyId(null);
    setMessage(outcome.ok ? { text: `${request.name} uploaded -- your counselor will review it.`, failed: false } : { text: outcome.message, failed: true });
    await load();
    if (outcome.ok) router.refresh(); // the documents list on this page shows the new upload
  }

  return (
    <div className="action-card">
      <h3>Requested documents</h3>
      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>
          {message.text}
        </div>
      )}
      {loadError ? (
        <div className="form-error" role="alert">
          {loadError}{" "}
          <button type="button" className="btn ghost small" onClick={load}>
            Try again
          </button>
        </div>
      ) : items === null ? (
        <p className="muted">Loading requested documents…</p>
      ) : items.length === 0 ? (
        <p className="muted">No documents are requested from you right now.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
          {items.map((r) => (
            <RequestRow key={r.id} request={r} busyId={busyId} onUpload={(file, expiry) => upload(r, file, expiry)} />
          ))}
        </ul>
      )}
    </div>
  );
}

function RequestRow({ request: r, busyId, onUpload }: { request: DocumentRequest; busyId: string | null; onUpload: (file: File | null, expiry: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [expiry, setExpiry] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    onUpload(file, expiry);
  }

  return (
    <li className="card" style={{ padding: 12 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        <strong>{r.name}</strong>
        {r.overdue && <span className="status error">Overdue</span>}
      </div>
      <p className="muted" style={{ fontSize: 13, margin: "2px 0 0" }}>
        {r.due_date && <>Due {formatCalendarDate(r.due_date)}</>}
        {r.university && <> · for {r.university}</>}
        {r.requested_by && <> · requested by {r.requested_by}</>}
      </p>
      {r.note && <p style={{ fontSize: 13, margin: "4px 0 0" }}>{r.note}</p>}
      {r.review_note && (
        <p className="form-error" style={{ fontSize: 13, margin: "6px 0 0" }}>
          Please upload a new file: {r.review_note}
        </p>
      )}
      <form className="form" onSubmit={submit} style={{ marginTop: 8 }}>
        <div className="form-grid">
          <div className="field">
            <label htmlFor={`request-file-${r.id}`}>File for {r.name}</label>
            <input id={`request-file-${r.id}`} type="file" accept={FILE_ACCEPT} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </div>
          <div className="field">
            <label htmlFor={`request-expiry-${r.id}`}>Expiry date (if the document has one)</label>
            <input id={`request-expiry-${r.id}`} type="date" value={expiry} onChange={(event) => setExpiry(event.target.value)} />
          </div>
        </div>
        <button className="btn small" disabled={busyId !== null}>
          {busyId === r.id ? "Uploading…" : "Upload"}
        </button>
      </form>
    </li>
  );
}

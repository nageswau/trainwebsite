"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { DOCUMENT_TYPES } from "@/lib/agentDocuments";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { DocumentRequest, REQUEST_STATUS_LABELS, RequestPage, staffRequestsUrl, todayInIndia } from "@/lib/documentRequests";
import { formatCalendarDate } from "@/lib/formatDate";

type Props = { studentId: string; applications: { id: string; label: string }[] };

// ccrm-020 (DEC-SCOPE-262): the student 360's Documents tab -- the counselor's / Overseas Admin's requests to this student (due date,
// overdue, the uploaded document's review status, Cancel while open) and the form to ask for one. One write at a time.
export default function CounselorDocumentRequestsPanel({ studentId, applications }: Props) {
  const url = staffRequestsUrl(studentId);
  const [items, setItems] = useState<DocumentRequest[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  const load = useCallback(async () => {
    setLoadError(null);
    const outcome = await sendRequest(url, {});
    if (!outcome.ok) return setLoadError(outcome.message);
    setItems((outcome.data as unknown as RequestPage).items ?? []);
  }, [url]);

  useEffect(() => {
    load();
  }, [load]);

  async function write(path: string, body: unknown, done: string): Promise<boolean> {
    if (inFlight.current) return false;
    inFlight.current = true;
    setBusy(true);
    setMessage(null);
    const outcome = await sendJson(url + path, "POST", body);
    inFlight.current = false;
    setBusy(false);
    setMessage(outcome.ok ? { text: done, failed: false } : { text: outcome.message, failed: true });
    load();
    return outcome.ok;
  }

  return (
    <section aria-label="Document requests" className="card" style={{ marginBottom: 12 }}>
      <h3 style={{ fontSize: 16, margin: "0 0 8px" }}>Document requests</h3>
      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} style={{ marginBottom: 8 }}>
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
        <p className="muted">Loading requests…</p>
      ) : items.length === 0 ? (
        <p className="muted">No document requests yet.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
          {items.map((r) => (
            <RequestRow key={r.id} request={r} busy={busy} onCancel={() => write(`/${r.id}/cancel`, {}, `Request for ${r.name} cancelled.`)} />
          ))}
        </ul>
      )}
      <RequestForm applications={applications} busy={busy} onSend={(body) => write("", body, "Request sent to the student.")} />
    </section>
  );
}

function RequestRow({ request: r, busy, onCancel }: { request: DocumentRequest; busy: boolean; onCancel: () => void }) {
  const tone = r.overdue ? "status error" : r.status === "open" ? "status pending" : r.status === "cancelled" ? "status closed" : "status";
  return (
    <li style={{ borderTop: "1px solid var(--line)", paddingTop: 8 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        <strong>{r.name}</strong>
        <span className={tone}>{r.overdue ? "Overdue" : REQUEST_STATUS_LABELS[r.status]}</span>
        {r.document && <span className="muted" style={{ fontSize: 13 }}>{r.document.original_filename || "Uploaded file"} — {r.document.status_label}</span>}
      </div>
      <p className="muted" style={{ fontSize: 13, margin: "2px 0 0" }}>
        {r.due_date && <>Due {formatCalendarDate(r.due_date)} · </>}
        {r.application_code ? `${r.application_code}${r.university ? ` · ${r.university}` : ""}` : "Not tied to an application"}
        {r.requested_by && <> · Requested by {r.requested_by}</>}
      </p>
      {r.note && <p style={{ fontSize: 13, margin: "2px 0 0" }}>Note: {r.note}</p>}
      {r.status === "open" && (
        <button type="button" className="btn ghost small" style={{ marginTop: 4 }} disabled={busy} aria-label={`Cancel request for ${r.name}`} onClick={onCancel}>
          Cancel request
        </button>
      )}
    </li>
  );
}

type Body = { document_type: string; document_label?: string; due_date: string; application_id?: string; note?: string };

function RequestForm({ applications, busy, onSend }: { applications: Props["applications"]; busy: boolean; onSend: (body: Body) => Promise<boolean> }) {
  const [documentType, setDocumentType] = useState<string>(DOCUMENT_TYPES[0]);
  const [label, setLabel] = useState("");
  const [due, setDue] = useState("");
  const [applicationId, setApplicationId] = useState("");
  const [note, setNote] = useState("");
  const other = documentType === "Other";

  async function submit(event: FormEvent) {
    event.preventDefault();
    const body: Body = { document_type: documentType, ...(other ? { document_label: label.trim() } : {}), due_date: due, ...(applicationId ? { application_id: applicationId } : {}), ...(note.trim() ? { note: note.trim() } : {}) };
    if (await onSend(body)) {
      setLabel("");
      setDue("");
      setNote("");
    }
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Request a document" style={{ marginTop: 12 }}>
      <h4 style={{ margin: 0, fontSize: 14 }}>Request a document</h4>
      <div className="form-grid">
        <div className="field">
          <label htmlFor="request-type">Document type</label>
          <select id="request-type" value={documentType} onChange={(event) => setDocumentType(event.target.value)}>
            {DOCUMENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        {other && (
          <div className="field">
            <label htmlFor="request-label">Name</label>
            <input id="request-label" value={label} minLength={2} maxLength={80} required onChange={(event) => setLabel(event.target.value)} />
          </div>
        )}
        <div className="field">
          <label htmlFor="request-due">Due date</label>
          <input id="request-due" type="date" required min={todayInIndia()} value={due} onChange={(event) => setDue(event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="request-application">Application (optional)</label>
          <select id="request-application" value={applicationId} onChange={(event) => setApplicationId(event.target.value)}>
            <option value="">Not tied to an application</option>
            {applications.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="field">
        <label htmlFor="request-note">Note to the student (optional)</label>
        <textarea id="request-note" maxLength={1000} value={note} onChange={(event) => setNote(event.target.value)} />
      </div>
      <button className="btn small" disabled={busy}>
        {busy ? "Sending…" : "Send request"}
      </button>
    </form>
  );
}

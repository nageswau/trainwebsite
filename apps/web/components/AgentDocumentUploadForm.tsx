"use client";

import { FormEvent, useEffect, useState } from "react";
import SearchableSelect from "@/components/SearchableSelect";
import { isPage, sendRequest } from "@/lib/apiErrors";
import { APPLICATIONS_URL, AgentApplicationItem } from "@/lib/agentApplications";
import AgentDocumentTypeField from "./AgentDocumentTypeField";
import { DOCUMENT_TYPES, documentName, DOCUMENTS_URL, DocumentRequestItem, FILE_ACCEPT, OFFER_LETTER, REQUESTS_URL, UPLOAD_DOCUMENT_TYPES } from "@/lib/agentDocuments";
import { searchAgentStudents } from "@/lib/agentStudents";

type Choices = { applications: AgentApplicationItem[]; requests: DocumentRequestItem[] };
const NONE: Choices = { applications: [], requests: [] };

// AGN-009 (AC1, G3/G5/G8): upload a document for one of the agency's students (with or without a login). The file goes to the
// server, which stores it and decides its type from the bytes. Picking an open request fulfils it. The student's applications and
// open requests load once a student is chosen.
export default function AgentDocumentUploadForm({ onUploaded }: { onUploaded: () => void }) {
  const [studentId, setStudentId] = useState("");
  const [type, setType] = useState<string>(DOCUMENT_TYPES[0]);
  const [choices, setChoices] = useState<Choices>(NONE);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [formVersion, setFormVersion] = useState(0);

  useEffect(() => {
    if (!studentId) return setChoices(NONE);
    const controller = new AbortController();
    const get = (url: string) =>
      fetch(url, { signal: controller.signal })
        .then((r) => r.json())
        .catch(() => null);
    Promise.all([get(`${APPLICATIONS_URL}?status=all&student=${studentId}&limit=100`), get(`${REQUESTS_URL}?status=open&student=${studentId}&limit=100`)]).then(([apps, requests]) => {
      if (controller.signal.aborted) return;
      setChoices({ applications: isPage<AgentApplicationItem>(apps) ? apps.items : [], requests: isPage<DocumentRequestItem>(requests) ? requests.items : [] });
    });
    return () => controller.abort();
  }, [studentId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !studentId) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const file = values.get("file");
    if (!(file instanceof File) || !file.size) return;
    const body = new FormData();
    body.set("agent_student_id", studentId);
    body.set("document_type", type);
    for (const key of ["document_label", "application_id", "request_id"]) {
      const value = String(values.get(key) ?? "").trim();
      if (value) body.set(key, value);
    }
    body.set("file", file);
    setBusy(true);
    setMessage(null);
    const outcome = await sendRequest(DOCUMENTS_URL, { method: "POST", body });
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: outcome.message, failed: true });
    setMessage({ text: "Document uploaded. It is waiting for review.", failed: false });
    form.reset();
    setType(DOCUMENT_TYPES[0]);
    setStudentId("");
    setFormVersion((v) => v + 1);
    onUploaded();
  }

  return (
    <section className="action-card" aria-labelledby="agent-doc-upload-heading">
      <h3 id="agent-doc-upload-heading">Upload document</h3>
      <form className="form" onSubmit={submit} aria-label="Upload document">
        <SearchableSelect key={formVersion} id="agent-doc-student" label="Student" required noun="student" search={searchAgentStudents} onChange={(option) => setStudentId(option?.id ?? "")} />
        <div className="form-grid">
          <AgentDocumentTypeField idPrefix="agent-doc" value={type} onChange={setType} types={UPLOAD_DOCUMENT_TYPES} />
          <div className="field">
            {/* AGN-010 O3: an offer letter belongs to one application (the server answers 422 without it). */}
            <label htmlFor="agent-doc-application">{type === OFFER_LETTER ? "Application (required for an offer letter)" : "Application (optional)"}</label>
            <select id="agent-doc-application" name="application_id" required={type === OFFER_LETTER} disabled={!choices.applications.length} defaultValue="">
              <option value="">{studentId ? (choices.applications.length ? "None" : "No applications") : "Choose a student first"}</option>
              {choices.applications.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.university}
                  {a.course ? ` — ${a.course}` : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="agent-doc-request">Fulfils request (optional)</label>
            <select id="agent-doc-request" name="request_id" disabled={!choices.requests.length} defaultValue="">
              <option value="">{studentId ? (choices.requests.length ? "None" : "No open requests") : "Choose a student first"}</option>
              {choices.requests.map((r) => (
                <option key={r.id} value={r.id}>
                  {documentName(r)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="field">
          <label htmlFor="agent-doc-file">File (PDF, JPEG or PNG)</label>
          <input id="agent-doc-file" name="file" type="file" accept={FILE_ACCEPT} required />
        </div>
        {message && (
          <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>
            {message.text}
          </p>
        )}
        <div className="actions">
          <button className="btn" disabled={busy}>
            {busy ? "Uploading…" : "Upload document"}
          </button>
        </div>
      </form>
    </section>
  );
}

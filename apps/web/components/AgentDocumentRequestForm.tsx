"use client";

import { FormEvent, useState } from "react";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import AgentDocumentTypeField from "./AgentDocumentTypeField";
import { DOCUMENT_TYPES, REQUESTS_URL } from "@/lib/agentDocuments";
import { searchAgentStudents } from "@/lib/agentStudents";

// AGN-009 (G4, AC4): Masters and staff ask one of their students for an additional document. The request stays under "Additional"
// until a document is uploaded against it. One open request per type and description (the server answers 409 otherwise).
export default function AgentDocumentRequestForm({ onCreated }: { onCreated: () => void }) {
  const [studentId, setStudentId] = useState("");
  const [type, setType] = useState<string>(DOCUMENT_TYPES[0]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [formVersion, setFormVersion] = useState(0);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !studentId) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const label = String(values.get("document_label") ?? "").trim();
    const note = String(values.get("note") ?? "").trim();
    setBusy(true);
    setMessage(null);
    const outcome = await sendJson(REQUESTS_URL, "POST", { agent_student_id: studentId, document_type: type, document_label: label || null, note: note || null });
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: outcome.message, failed: true });
    setMessage({ text: "Request added to Additional documents.", failed: false });
    form.reset();
    setType(DOCUMENT_TYPES[0]);
    setStudentId("");
    setFormVersion((v) => v + 1);
    onCreated();
  }

  return (
    <section className="action-card" aria-labelledby="agent-doc-request-heading">
      <h3 id="agent-doc-request-heading">Request a document</h3>
      <form className="form" onSubmit={submit} aria-label="Request a document">
        <SearchableSelect key={formVersion} id="agent-request-student" label="Student" required noun="student" search={searchAgentStudents} onChange={(option) => setStudentId(option?.id ?? "")} />
        <div className="form-grid">
          <AgentDocumentTypeField idPrefix="agent-request" value={type} onChange={setType} />
        </div>
        <div className="field">
          <label htmlFor="agent-request-note">Note for the file (optional)</label>
          <textarea id="agent-request-note" name="note" maxLength={1000} style={{ minHeight: 80 }} />
        </div>
        {message && (
          <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>
            {message.text}
          </p>
        )}
        <div className="actions">
          <button className="btn" disabled={busy}>
            {busy ? "Saving…" : "Add request"}
          </button>
        </div>
      </form>
    </section>
  );
}

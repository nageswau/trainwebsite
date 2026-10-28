"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useRef, useState } from "react";

import { FILE_ACCEPT, OFFER_LETTER, OTHER, UPLOAD_DOCUMENT_TYPES } from "@/lib/agentDocuments";
import { sendRequest } from "@/lib/apiErrors";

type Props = { studentId: string; applications: { id: string; label: string }[] };

// ccrm-045 (DEC-SCOPE-316): the student 360's Documents tab -- the counselor / Overseas Admin uploads a document for the student, with or
// without one of their applications; the student sees it at once. An offer letter belongs to an application. One upload at a time.
export default function CounselorDocumentUpload({ studentId, applications }: Props) {
  const router = useRouter();
  const types = applications.length ? UPLOAD_DOCUMENT_TYPES : UPLOAD_DOCUMENT_TYPES.filter((t) => t !== OFFER_LETTER);
  const [documentType, setDocumentType] = useState<string>(types[0]);
  const [label, setLabel] = useState("");
  const [applicationId, setApplicationId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const inFlight = useRef(false);
  const offer = documentType === OFFER_LETTER;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    if (inFlight.current || !file) return;
    inFlight.current = true;
    setBusy(true);
    setMessage(null);
    const form = new FormData();
    form.append("document_type", documentType);
    if (documentType === OTHER) form.append("document_label", label.trim());
    if (applicationId) form.append("application_id", applicationId);
    form.append("file", file);
    const outcome = await sendRequest(`/api/v1/counselor/students/${encodeURIComponent(studentId)}/documents`, { method: "POST", body: form });
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: outcome.message, failed: true });
    setMessage({ text: "Uploaded. The student can see it in their Documents.", failed: false });
    setLabel("");
    if (fileInput.current) fileInput.current.value = "";
    router.refresh();
  }

  return (
    <section aria-label="Upload a document for the student" className="card" style={{ marginBottom: 12 }}>
      <h3 style={{ fontSize: 16, margin: "0 0 8px" }}>Upload a document</h3>
      <p className="muted" style={{ marginTop: 0 }}>PDF, JPEG or PNG, up to 20 MB. The student sees it in their Documents straight away.</p>
      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} style={{ marginBottom: 8 }}>
          {message.text}
        </div>
      )}
      <form className="form" onSubmit={submit} aria-label="Upload a document">
        <div className="form-grid">
          <div className="field">
            <label htmlFor="upload-type">Document type</label>
            <select
              id="upload-type"
              value={documentType}
              onChange={(event) => {
                setDocumentType(event.target.value);
                if (event.target.value === OFFER_LETTER && !applicationId) setApplicationId(applications[0]?.id ?? "");
              }}
            >
              {types.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          {documentType === OTHER && (
            <div className="field">
              <label htmlFor="upload-label">Name</label>
              <input id="upload-label" value={label} minLength={2} maxLength={80} required onChange={(event) => setLabel(event.target.value)} />
            </div>
          )}
          {applications.length > 0 && (
            <div className="field">
              <label htmlFor="upload-application">Application</label>
              <select id="upload-application" value={applicationId} required={offer} onChange={(event) => setApplicationId(event.target.value)}>
                {!offer && <option value="">Not tied to an application</option>}
                {applications.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="field">
            <label htmlFor="upload-file">File</label>
            <input id="upload-file" ref={fileInput} type="file" accept={FILE_ACCEPT} required />
          </div>
        </div>
        <button className="btn small" disabled={busy}>
          {busy ? "Uploading…" : "Upload document"}
        </button>
      </form>
    </section>
  );
}

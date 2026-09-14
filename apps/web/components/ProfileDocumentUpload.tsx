"use client";

import { FormEvent, useEffect, useState } from "react";

type ProfileDocumentRow = { id: string; document_type: string; file_url: string; original_filename: string | null; uploaded_at: string };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Upload failed.";
}

// STU-011: "Maintain own profile... upload documents (CV/portfolio)." Profile field
// editing already existed (`PATCH /auth/me`, wired above this panel); document
// management genuinely did not -- `StudentDocument` is Overseas-division-specific (FK to
// `overseas_applications`, gated to overseas roles), not reusable here. This reuses the
// same presign-then-upload flow as the Overseas `DocumentUpload` panel, but posts to the
// new self-scoped `/workflows/it/student/profile/documents`, which re-validates
// content-type/size at the record-creation step (STU-011-AC02) rather than trusting
// whatever `file_url` the client hands it.
export default function ProfileDocumentUpload() {
  const [rows, setRows] = useState<ProfileDocumentRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<{ id: string; text: string } | null>(null);

  async function download(row: ProfileDocumentRow) {
    setDownloadingId(row.id);
    setDownloadError(null);
    const response = await fetch(`/api/v1/workflows/it/student/profile/documents/${row.id}/download`);
    const data = await response.json().catch(() => ({}));
    setDownloadingId(null);
    if (!response.ok) {
      setDownloadError({ id: row.id, text: detailMessage(data.detail) });
      return;
    }
    window.open(data.url, "_blank", "noreferrer");
  }

  function load() {
    fetch("/api/v1/workflows/it/student/profile/documents")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setRows(data))
      .catch(() => setRows([]));
  }

  useEffect(load, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setFailed(false);
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const file = form.get("file");
    if (!(file instanceof File) || !file.size) {
      setBusy(false);
      return;
    }
    try {
      let fileUrl = "";
      const local = new FormData();
      local.set("file", file);
      const localResponse = await fetch("/api/v1/files/local-upload", { method: "POST", body: local });
      if (localResponse.ok) fileUrl = String((await localResponse.json()).url);
      else {
        const presignResponse = await fetch("/api/v1/files/presign", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename: file.name, content_type: file.type, size: file.size }) });
        const signed = await presignResponse.json();
        if (!presignResponse.ok) throw new Error(detailMessage(signed.detail));
        const upload = await fetch(signed.upload_url, { method: "PUT", headers: { "Content-Type": file.type }, body: file });
        if (!upload.ok) throw new Error("Object storage upload failed");
        fileUrl = signed.key;
      }
      const response = await fetch("/api/v1/workflows/it/student/profile/documents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_type: form.get("document_type"), file_url: fileUrl, original_filename: file.name, content_type: file.type, file_size: file.size }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(detailMessage(data.detail));
      setMessage("Document uploaded.");
      formElement.reset();
      load();
    } catch (error) {
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="action-card">
      <h3>Documents</h3>
      <p className="muted">Upload your CV, portfolio, or other supporting documents. Configured file types and sizes only.</p>
      {rows && rows.length > 0 && (
        <ul className="list-clean" style={{ marginTop: 8, marginBottom: 8 }}>
          {rows.map((row) => (
            <li key={row.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
              <span>{row.document_type} -- {row.original_filename || row.file_url}</span>
              <span>
                <button type="button" className="btn small secondary" disabled={downloadingId === row.id} onClick={() => download(row)}>
                  {downloadingId === row.id ? "Preparing…" : "Download"}
                </button>
                {downloadError?.id === row.id && <span className="form-error" role="alert" style={{ marginLeft: 8, fontSize: 12 }}>{downloadError.text}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="profile-document-type">Document type</label>
          <input id="profile-document-type" name="document_type" required placeholder="Resume, portfolio, ID proof…" />
        </div>
        <div className="field">
          <label htmlFor="profile-document-file">File</label>
          <input id="profile-document-file" name="file" type="file" required />
        </div>
        {message && <div className={failed ? "form-error" : "form-message"} role="status" aria-live="polite">{message}</div>}
        <button className="btn small" disabled={busy}>{busy ? "Uploading…" : "Upload document"}</button>
      </form>
    </div>
  );
}

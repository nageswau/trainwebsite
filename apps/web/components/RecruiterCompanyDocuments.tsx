"use client";
import { type FormEvent, useEffect, useState } from "react";

import { sendRequest } from "@/lib/apiErrors";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { refocus } from "@/lib/focus";
import { personName } from "@/lib/recruiterCompanies";
import {
  AGREEMENT, type CompanyDocument, DOCUMENT_KINDS, type DocumentKind, type DocumentPage, documentsUrl, downloadUrl, fileSize, isDocumentPage, KIND_LABEL,
} from "@/lib/recruiterCompanyDocuments";
import { meetingTypeLabel } from "@/lib/recruiterMeetings";

const PAGE = 50;
const MAX_BYTES = 20 * 1024 * 1024; // the API's max_upload_bytes; fast feedback only, the server re-checks by content
const TYPES = ["application/pdf", "image/jpeg", "image/png"];
const SERVER_FAILED = "Something went wrong on our side. Please try again.";
type MeetingOption = { id: string; code: string; meeting_type: string; starts_at: string };

// pob-003 (DEC-SCOPE-406 D6-D8): the company's files -- profile, vendor form, agreement, JDs, meeting notes. Downloads are plain links to
// the scoped route (the API audits and streams an attachment); `can_download` is false for an agreement without commercial access. The
// upload form shows with `can_upload` (the assigned recruiter / super admin), the agreement type only with `can_upload_agreement`.
export default function RecruiterCompanyDocuments({ companyId, onUploaded }: { companyId: string; onUploaded?: () => void }) {
  const [data, setData] = useState<DocumentPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [kind, setKind] = useState<DocumentKind | "">("");
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);
  const [meetings, setMeetings] = useState<MeetingOption[]>([]);
  const [upload, setUpload] = useState<{ kind: DocumentKind; meeting: string; file: File | null }>({ kind: "company_profile", meeting: "", file: null });
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const titleId = `company-${companyId}-documents`;
  const fileId = `company-${companyId}-document-file`;
  const canUpload = data?.can_upload ?? false;

  useEffect(() => {
    let live = true;
    setFailed(false);
    const query = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
    if (kind) query.set("kind", kind);
    fetch(`${documentsUrl(companyId)}?${query}`)
      .then(async (r) => {
        const body = await r.json().catch(() => null);
        if (!r.ok || !isDocumentPage(body)) throw new Error("not a page");
        if (live) setData(body);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [companyId, kind, offset, version]);

  // The meeting picker: only for an uploader; a failed read leaves just "No meeting".
  useEffect(() => {
    if (!canUpload) return;
    const abort = new AbortController();
    fetch(`/api/v1/recruiter/companies/${companyId}/meetings?limit=50`, { signal: abort.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => body && Array.isArray(body.items) && setMeetings(body.items), () => undefined);
    return () => abort.abort();
  }, [companyId, canUpload]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setNotice(null);
    const file = upload.file;
    if (!file) return setFailure("Choose a file to upload.");
    if (!TYPES.includes(file.type)) return setFailure("Upload a PDF, JPEG or PNG file.");
    if (file.size > MAX_BYTES) return setFailure("The file must be at most 20 MB.");
    setFailure(null);
    setBusy(true);
    const body = new FormData();
    body.append("kind", upload.kind);
    if (upload.meeting) body.append("meeting_id", upload.meeting);
    body.append("file", file);
    const outcome = await sendRequest(documentsUrl(companyId), { method: "POST", body });
    setBusy(false);
    if (outcome.ok) {
      setUpload((u) => ({ ...u, meeting: "", file: null }));
      setFileKey((k) => k + 1); // a fresh file input: the chosen file is cleared
      setNotice("Document uploaded.");
      setOffset(0);
      setVersion((v) => v + 1);
      onUploaded?.(); // pob-010: a vendor's "on file" lines
      return;
    }
    setFailure((outcome.status ?? 0) >= 500 ? SERVER_FAILED : outcome.message);
    refocus(fileId);
  }

  const kinds = DOCUMENT_KINDS.filter((k) => k !== AGREEMENT || data?.can_upload_agreement);
  const row = (d: CompanyDocument) => (
    <tr key={d.id}>
      <td data-label="Type">{KIND_LABEL[d.kind]}</td>
      <td data-label="File" style={{ minWidth: 140 }}>
        {d.name ?? "Untitled"} <span className="muted">({d.content_type === "application/pdf" ? "PDF" : "image"}, {fileSize(d.size_bytes)})</span>
      </td>
      <td data-label="Meeting">{d.meeting ? d.meeting.code : "—"}</td>
      <td data-label="Uploaded by">{personName(d.uploaded_by)}</td>
      <td data-label="Uploaded" style={{ whiteSpace: "nowrap" }}>{formatSchoolDateTime(d.created_at)}</td>
      <td data-label="Download">
        {d.can_download ? (
          <a className="btn ghost small" href={downloadUrl(d.id)} download aria-label={`Download ${d.name ?? KIND_LABEL[d.kind]}`}>
            Download
          </a>
        ) : (
          <span className="muted">Needs commercial access</span>
        )}
      </td>
    </tr>
  );

  return (
    <section className="action-card wide telecaller-list" aria-labelledby={titleId} aria-busy={data === null && !failed}>
      <h3 id={titleId}>Documents</h3>
      <div role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      {canUpload && (
        <form className="form" onSubmit={(e) => void submit(e)} noValidate style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
          <div className="field" style={{ flex: "1 1 180px", margin: 0 }}>
            <label htmlFor={`${titleId}-kind`}>Document type</label>
            <select id={`${titleId}-kind`} value={upload.kind} onChange={(e) => setUpload((u) => ({ ...u, kind: e.target.value as DocumentKind }))}>
              {kinds.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
            </select>
          </div>
          <div className="field" style={{ flex: "1 1 200px", margin: 0 }}>
            <label htmlFor={`${titleId}-meeting`}>Linked meeting (optional)</label>
            <select id={`${titleId}-meeting`} value={upload.meeting} onChange={(e) => setUpload((u) => ({ ...u, meeting: e.target.value }))}>
              <option value="">No meeting</option>
              {meetings.map((m) => (
                <option key={m.id} value={m.id}>{m.code} · {meetingTypeLabel(m.meeting_type)} · {formatSchoolDateTime(m.starts_at)}</option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: "1 1 220px", margin: 0 }}>
            <label htmlFor={fileId}>File (PDF, JPEG or PNG, up to 20 MB)</label>
            <input key={fileKey} id={fileId} type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" disabled={busy}
              onChange={(e) => setUpload((u) => ({ ...u, file: e.target.files?.[0] ?? null }))} />
          </div>
          <button type="submit" className="btn small" disabled={busy} aria-label="Upload document">
            {busy ? "Uploading…" : "Upload"}
          </button>
        </form>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      <div className="field" style={{ maxWidth: 240 }}>
        <label htmlFor={`${titleId}-filter`}>Show</label>
        <select id={`${titleId}-filter`} value={kind} onChange={(e) => { setKind(e.target.value as DocumentKind | ""); setOffset(0); }}>
          <option value="">All types</option>
          {DOCUMENT_KINDS.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
        </select>
      </div>
      {failed ? (
        <>
          <p className="form-error" role="alert">Unable to load documents.</p>
          <button type="button" className="btn secondary small" aria-label="Retry documents" onClick={() => setVersion((v) => v + 1)}>Retry</button>
        </>
      ) : data === null ? (
        <p className="muted" role="status">Loading documents…</p>
      ) : data.items.length === 0 ? (
        <p className="empty">{kind ? "No documents of this type." : "No documents yet."}</p>
      ) : (
        <>
          <div className="table-wrap" role="region" aria-label="Company documents" tabIndex={0}>
            <table style={{ width: "100%", overflowWrap: "anywhere" }}>
              <thead>
                <tr>
                  <th scope="col">Type</th>
                  <th scope="col">File</th>
                  <th scope="col">Meeting</th>
                  <th scope="col">Uploaded by</th>
                  <th scope="col">Uploaded</th>
                  <th scope="col"><span className="visually-hidden">Download</span></th>
                </tr>
              </thead>
              <tbody>{data.items.map(row)}</tbody>
            </table>
          </div>
          {data.total > PAGE && (
            <nav aria-label="Document pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE))}>Previous</button>
              <button type="button" className="btn secondary small" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset((o) => o + PAGE)}>Next</button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}

"use client";

import { type FormEvent, useRef, useState } from "react";

import DocumentFileActions from "@/components/DocumentFileActions";
import LocalTime from "@/components/LocalTime";
import RecruiterResumeExtraction from "@/components/RecruiterResumeExtraction";
import { sendRequest } from "@/lib/apiErrors";
import { RESUME_ACCEPT, RESUME_MAX_BYTES, candidateUrl, fileSize, resumeLinkUrl, type CandidateResume } from "@/lib/recruiterCandidates";
import type { CurrentProfile } from "@/lib/recruiterResumeExtract";

// rec-009 (AC4, Q-09 default): the resume versions, newest first -- the first is current -- and, for writers, an upload of a new
// version (PDF, DOC or DOCX since hrc-015, at most 5 MB; the API judges the type by the bytes). hrc-015 (D3/D4): Preview and Download
// go through short-lived signed links the API audits (DocumentFileActions).
// rec-012 (EX1): an upload opens "Review extracted details" for the new version; writers can reopen it on the current version.
type Props = {
  candidateId: string; resumes: CandidateResume[]; canUpload: boolean; current: CurrentProfile; onUploaded: () => void; onApplied: () => void;
};

export default function RecruiterCandidateResumes({ candidateId, resumes, canUpload, current, onUploaded, onApplied }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const sending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const [reviewing, setReviewing] = useState<number | null>(null);

  async function upload(event: FormEvent) {
    event.preventDefault();
    const file = input.current?.files?.[0];
    if (!file) return setNotice({ text: "Choose a PDF, DOC or DOCX file first.", failed: true });
    if (file.size > RESUME_MAX_BYTES) return setNotice({ text: "The resume must be at most 5 MB.", failed: true });
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setNotice(null);
    const form = new FormData();
    form.append("file", file);
    const outcome = await sendRequest(candidateUrl(candidateId, "/resume"), { method: "PUT", body: form });
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    if (input.current) input.current.value = "";
    if (outcome.data.content_type === "application/msword") {
      // hrc-015 QA-01: a DOC is read through its PDF rendition, which the worker is still preparing -- offer the review later instead
      setNotice({ text: `Resume version ${outcome.data.version} uploaded. Its preview and extracted details will be ready in a moment.`, failed: false });
    } else {
      setNotice({ text: `Resume version ${outcome.data.version} uploaded.`, failed: false });
      setReviewing(Number(outcome.data.version));
    }
    onUploaded();
  }

  return (
    <section aria-labelledby="cand-resume-heading" className="action-card" style={{ display: "grid", gap: 12 }}>
      <h3 id="cand-resume-heading" style={{ margin: 0 }}>Resume</h3>
      {resumes.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No resume uploaded yet.</p>
      ) : (
        <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", display: "grid", gap: 8 }}>
          {resumes.map((r, i) => (
            <li key={r.version} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
              <span style={{ fontWeight: i === 0 ? 600 : undefined, overflowWrap: "anywhere" }}>
                Version {r.version}{r.file_name ? ` — ${r.file_name}` : ""}
              </span>
              {i === 0 && <span className="badge">Current</span>}
              <span className="muted" style={{ fontSize: 13 }}>
                {fileSize(r.size_bytes)} · <LocalTime value={r.created_at} time />{r.uploaded_by ? ` · ${r.uploaded_by.full_name}` : ""}
              </span>
              {i === 0 && canUpload && reviewing === null && (
                <button type="button" className="btn secondary small" onClick={() => { setNotice(null); setReviewing(r.version); }}>Review extracted details</button>
              )}
              <DocumentFileActions linkUrl={resumeLinkUrl(candidateId, r.version)} contentType={r.content_type} label={`resume version ${r.version}`} />
            </li>
          ))}
        </ul>
      )}
      {reviewing !== null && canUpload && (
        <RecruiterResumeExtraction key={reviewing} candidateId={candidateId} version={reviewing} current={current} onClose={() => setReviewing(null)}
          onApplied={(text) => { setReviewing(null); setNotice({ text, failed: false }); onApplied(); }} />
      )}
      {canUpload && (
        <form onSubmit={upload} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
          <div className="field" style={{ flex: "1 1 16rem", marginBottom: 0 }}>
            <label htmlFor="cand-resume-file">{resumes.length ? "Upload a new version" : "Upload resume"}</label>
            <span id="cand-resume-hint" className="muted" style={{ fontSize: 13 }}>PDF, DOC or DOCX, up to 5 MB</span>
            <input id="cand-resume-file" ref={input} type="file" accept={RESUME_ACCEPT} aria-describedby="cand-resume-hint" disabled={busy} />
          </div>
          <button type="submit" className="btn secondary small" disabled={busy}>{busy ? "Uploading…" : "Upload"}</button>
        </form>
      )}
      {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0, fontSize: 13 }}>{notice.text}</p>}
    </section>
  );
}

"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendRequest } from "@/lib/apiErrors";
import { fileSize } from "@/lib/recruiterCandidates";
import { megabytes, RESUME_ACCEPT, resumeFileUrl, uploaderLabel, type StudentResumeList } from "@/lib/studentResumes";

type Notice = { text: string; failed: boolean };
const LOAD_FAILED = "The resume versions could not be loaded.";

// itc-026 (DEC-SCOPE-350): one IT student's resume versions, newest first (the first is current), and -- when the API says so
// (`can_upload`) -- an upload of a new version. The student, their counselor and the IT Admin upload; HR reads `hr` versions only.
// Downloads are plain links: the API writes an access-log row for each one before sending the file.
// `hrView` (QA-01): HR sees only shared versions, so its newest is "Latest shared" (the student may have a newer private one).
export default function StudentResumeCard({ url, canDownload = true, hrView = false, description }: { url: string; canDownload?: boolean; hrView?: boolean; description?: string }) {
  const input = useRef<HTMLInputElement>(null);
  const sending = useRef(false);
  const [data, setData] = useState<StudentResumeList | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [share, setShare] = useState(true);
  const [notice, setNotice] = useState<Notice | null>(null);

  const load = useCallback(async () => {
    setLoadError(false);
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      setData(await response.json());
    } catch {
      setLoadError(true);
    }
  }, [url]);

  useEffect(() => { void load(); }, [load]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!data || sending.current) return;
    const file = input.current?.files?.[0];
    if (!file) return setNotice({ text: "Choose a PDF, DOC or DOCX file first.", failed: true });
    if (file.size > data.max_bytes) return setNotice({ text: `The resume must be at most ${megabytes(data.max_bytes)}.`, failed: true });
    sending.current = true;
    setBusy(true);
    setNotice(null);
    const form = new FormData();
    form.append("file", file);
    form.append("visibility", share ? "hr" : "private");
    const outcome = await sendRequest(url, { method: "POST", body: form });
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    if (input.current) input.current.value = "";
    setNotice({ text: `Resume version ${outcome.data.version} uploaded.`, failed: false });
    await load();
  }

  return (
    <section aria-labelledby="student-resume-heading" className="action-card" style={{ display: "grid", gap: 12 }}>
      <h3 id="student-resume-heading" style={{ margin: 0 }}>Resume</h3>
      {description && <p className="muted" style={{ margin: 0 }}>{description}</p>}
      {loadError ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>
          {LOAD_FAILED} <button type="button" className="btn secondary small" onClick={() => void load()}>Try again</button>
        </p>
      ) : !data ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading resume versions…</p>
      ) : data.items.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No resume uploaded yet.</p>
      ) : (
        <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", display: "grid", gap: 8 }}>
          {data.items.map((r, i) => {
            const label = `Version ${r.version}${r.file_name ? ` — ${r.file_name}` : ""}`;
            const uploader = uploaderLabel(r);
            return (
              <li key={r.version} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
                {canDownload ? (
                  <a href={resumeFileUrl(url, r.version)} download style={{ fontWeight: i === 0 ? 600 : undefined, overflowWrap: "anywhere" }}>{label}</a>
                ) : (
                  <span style={{ fontWeight: i === 0 ? 600 : undefined, overflowWrap: "anywhere" }}>{label}</span>
                )}
                {i === 0 && <span className="badge">{hrView ? "Latest shared" : "Current"}</span>}
                {!hrView && <span className="badge">{r.visibility === "hr" ? "Shared with HR" : "Not shared with HR"}</span>}
                <span className="muted" style={{ fontSize: 13 }}>
                  {fileSize(r.size_bytes)} · <LocalTime value={r.created_at} time />{uploader ? ` · ${uploader}` : ""}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {data?.can_upload && (
        <form onSubmit={upload} style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
          <div className="field" style={{ flex: "1 1 16rem", marginBottom: 0 }}>
            <label htmlFor="student-resume-file">{data.items.length ? "Upload a new version" : "Upload resume"}</label>
            <span id="student-resume-hint" className="muted" style={{ fontSize: 13 }}>PDF, DOC or DOCX, up to {megabytes(data.max_bytes)}. Earlier versions are kept.</span>
            <input id="student-resume-file" ref={input} type="file" accept={RESUME_ACCEPT} aria-describedby="student-resume-hint" disabled={busy} />
          </div>
          <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <input type="checkbox" checked={share} onChange={(e) => setShare(e.target.checked)} disabled={busy} /> Share with HR
          </label>
          <button type="submit" className="btn secondary small" disabled={busy} aria-busy={busy}>{busy ? "Uploading…" : "Upload"}</button>
        </form>
      )}
      {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0, fontSize: 13 }}>{notice.text}</p>}
    </section>
  );
}

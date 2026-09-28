"use client";

import { ChangeEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { detailMessage } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";

const MAX_BYTES = 5 * 1024 * 1024;
const TYPES = ["application/pdf", "image/jpeg", "image/png"];

// ENH-021 (I5): the certificate of a completed internship. Readers get a download link; writers also upload, replace and remove it
// (two-step remove, like the student photo). Client checks are fast feedback only -- the server re-validates by content.
export default function InternshipCertificate({ studentId, entryId, hasCertificate, contentType, canEdit, completed }: {
  studentId: string; entryId: string; hasCertificate: boolean; contentType: string | null; canEdit: boolean; completed: boolean;
}) {
  // QA-01: after a change the server data behind the page must be re-read (router.refresh, the portfolio's own pattern);
  // otherwise a remount -- e.g. Edit then Cancel -- starts again from the stale `hasCertificate` prop.
  const router = useRouter();
  const [present, setPresent] = useState(hasCertificate);
  const [kind, setKind] = useState(contentType);
  const [busy, setBusy] = useState<"upload" | "remove" | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const url = `/api/v1/school/students/${studentId}/portfolio/entries/${entryId}/certificate`;
  const inputId = `cert-${entryId}`;
  const writable = canEdit && completed;

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    if (!TYPES.includes(file.type)) return setMessage({ text: "Certificate must be a PDF, JPEG or PNG file", failed: true });
    if (file.size > MAX_BYTES) return setMessage({ text: "Certificate must be at most 5 MB", failed: true });
    setBusy("upload");
    setMessage(null);
    const body = new FormData();
    body.append("file", file);
    const response = await fetch(url, { method: "PUT", body }).catch(() => null);
    const data = response ? await response.json().catch(() => ({})) : {};
    setBusy(null);
    input.value = "";
    refocus(inputId);
    if (!response?.ok) return setMessage({ text: detailMessage(data.detail, "Upload failed; please try again."), failed: true });
    setPresent(true);
    setKind(data.content_type ?? file.type);
    setMessage({ text: "Certificate saved.", failed: false });
    router.refresh();
  }

  async function remove() {
    setBusy("remove");
    setMessage(null);
    const response = await fetch(url, { method: "DELETE" }).catch(() => null);
    setBusy(null);
    setConfirming(false);
    if (!response?.ok) return setMessage({ text: "Could not remove the certificate; please try again.", failed: true });
    setPresent(false);
    setMessage({ text: "Certificate removed.", failed: false });
    refocus(inputId);  // QA-06: the Confirm button just unmounted; keep keyboard users in place
    router.refresh();
  }

  if (!present && !writable && !message) return null;
  return (
    <div className="field internship-certificate">
      {present && <a className="btn ghost small" href={url} download>Download certificate ({kind === "application/pdf" ? "PDF" : "image"})</a>}
      {writable && (
        <>
          <label htmlFor={inputId}>{present ? "Replace certificate" : "Upload certificate"} (PDF, JPEG or PNG, up to 5 MB)</label>
          <input id={inputId} type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={upload} disabled={busy !== null} />
          {busy === "upload" && <span className="muted" aria-live="polite">Uploading…</span>}
          {present && !confirming && <button type="button" className="btn ghost small" onClick={() => setConfirming(true)} disabled={busy !== null}>Remove certificate</button>}
          {confirming && (
            <div className="actions">
              <button type="button" className="btn small" onClick={remove} disabled={busy !== null}>{busy === "remove" ? "Removing…" : "Confirm remove"}</button>
              <button type="button" className="btn secondary small" onClick={() => setConfirming(false)}>Cancel</button>
            </div>
          )}
        </>
      )}
      {message && (message.failed ? <div className="form-error" role="alert">{message.text}</div> : <div className="form-message" role="status" aria-live="polite">{message.text}</div>)}
    </div>
  );
}

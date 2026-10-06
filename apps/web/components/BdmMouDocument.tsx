"use client";
import { type ChangeEvent, useState } from "react";

import { sendRequest } from "@/lib/apiErrors";
import { isMouBody, type Mou, mouDocumentUrl, orgMouUrl } from "@/lib/bdmMous";
import { formatDate } from "@/lib/formatDate";
import { refocus } from "@/lib/focus";

const MAX_BYTES = 20 * 1024 * 1024; // the API's max_upload_bytes; fast feedback only, the server re-checks by content
const TYPES = ["application/pdf", "image/jpeg", "image/png"];
const WRONG_FILE = "Upload a PDF, JPEG or PNG file";
const SERVER_FAILED = "Something went wrong on our side. Please try again.";

// bdm-005 (M4, AC4; the InternshipCertificate pattern): the MoU's one document. The download is a plain link to the scoped route (the
// API checks scope, audits, and streams it as an attachment); the upload is a multipart PUT for the assigned BDM / super_admin.
export default function BdmMouDocument({ orgId, mou, onUploaded }: { orgId: string; mou: Mou; onUploaded: (m: Mou) => void }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const inputId = `mou-${mou.id}-file`;
  const doc = mou.document;

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    setFailure(null);
    if (!TYPES.includes(file.type)) return setFailure(WRONG_FILE);
    if (file.size > MAX_BYTES) return setFailure("The file must be at most 20 MB");
    setBusy(true);
    const body = new FormData();
    body.append("file", file);
    const outcome = await sendRequest(`${orgMouUrl(orgId)}/document`, { method: "PUT", body });
    setBusy(false);
    input.value = "";
    refocus(inputId);
    if (outcome.ok && isMouBody(outcome.data)) return onUploaded(outcome.data.mou);
    setFailure(outcome.ok || (outcome.status ?? 0) >= 500 ? SERVER_FAILED : outcome.message);
  }

  return (
    <div className="field">
      {doc ? (
        <p style={{ margin: 0 }}>
          Document: {doc.name ?? "on file"} · uploaded {formatDate(doc.uploaded_at)}{" "}
          <a className="btn ghost small" href={mouDocumentUrl(mou.id)} download>
            Download document ({doc.content_type === "application/pdf" ? "PDF" : "image"})
          </a>
        </p>
      ) : (
        <p className="muted" style={{ margin: 0 }}>No document on file.</p>
      )}
      {mou.permissions.can_upload && (
        <>
          <label htmlFor={inputId}>{doc ? "Replace document" : "Upload document"} (PDF, JPEG or PNG, up to 20 MB)</label>
          <input id={inputId} type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={upload} disabled={busy} />
          {busy && <span className="muted" aria-live="polite">Uploading…</span>}
        </>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
    </div>
  );
}

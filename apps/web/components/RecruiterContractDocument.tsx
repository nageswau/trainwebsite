"use client";
import { type ChangeEvent, useState } from "react";

import { sendRequest } from "@/lib/apiErrors";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { refocus } from "@/lib/focus";
import { companyContractsUrl, type Contract, contractDocumentUrl, DOCUMENT_LABEL, type DocumentKind, isContractBody } from "@/lib/recruiterContracts";

const MAX_BYTES = 20 * 1024 * 1024; // the API's max_upload_bytes; fast feedback only, the server re-checks by content
const TYPES = ["application/pdf", "image/jpeg", "image/png"];
const WRONG_FILE = "Upload a PDF, JPEG or PNG file";
const SERVER_FAILED = "Something went wrong on our side. Please try again.";

// rec-030 (CT3; the BdmMouDocument pattern): one of the contract's two files. The download is a plain link to the scoped route (the API
// checks scope, audits, and streams it as an attachment); the upload is a multipart PUT for the assigned recruiter / super_admin.
export default function RecruiterContractDocument({ companyId, contract, kind, onUploaded }: {
  companyId: string; contract: Contract; kind: DocumentKind; onUploaded: (c: Contract) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const inputId = `contract-${contract.id}-${kind}-file`;
  const doc = kind === "contract" ? contract.contract_document : contract.mou_document;
  const label = DOCUMENT_LABEL[kind];

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
    const outcome = await sendRequest(`${companyContractsUrl(companyId)}/document?kind=${kind}`, { method: "PUT", body });
    setBusy(false);
    input.value = "";
    refocus(inputId);
    if (outcome.ok && isContractBody(outcome.data)) return onUploaded(outcome.data.contract);
    setFailure(outcome.ok || (outcome.status ?? 0) >= 500 ? SERVER_FAILED : outcome.message);
  }

  return (
    <div className="field">
      {doc ? (
        <p style={{ margin: 0 }}>
          {label}: {doc.name ?? "on file"} · uploaded {formatSchoolDateTime(doc.uploaded_at, true)}{" "}
          <a className="btn ghost small" href={contractDocumentUrl(contract.id, kind)} download>
            Download {label.toLowerCase()} ({doc.content_type === "application/pdf" ? "PDF" : "image"})
          </a>
        </p>
      ) : (
        <p className="muted" style={{ margin: 0 }}>No {label.toLowerCase()} on file.</p>
      )}
      {contract.permissions.can_upload && (
        <>
          <label htmlFor={inputId}>{doc ? `Replace ${label.toLowerCase()}` : `Upload ${label.toLowerCase()}`} (PDF, JPEG or PNG, up to 20 MB)</label>
          <input id={inputId} type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={upload} disabled={busy} />
          {busy && <span className="muted" aria-live="polite">Uploading…</span>}
        </>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
    </div>
  );
}

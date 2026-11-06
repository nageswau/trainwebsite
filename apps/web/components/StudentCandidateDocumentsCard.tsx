"use client";

import { useCallback, useEffect, useState } from "react";

import CandidateDocumentUploadForm from "@/components/CandidateDocumentUploadForm";
import DocumentFileActions from "@/components/DocumentFileActions";
import LocalTime from "@/components/LocalTime";
import { type DocumentsState, MY_DOCUMENTS_URL, REQUEST_STATUS_LABELS, documentCompletion, documentName, documentTypeLabel } from "@/lib/candidateDocuments";
import { fileSize } from "@/lib/recruiterCandidates";

// hrc-015 (DEC-SCOPE-379 D8): an IT student in the placement candidate pool sees the documents the placement team asked for, uploads
// them (or a certificate of their own) and opens what they shared. Only ever the caller's own records; staff are never named.
type MyDocuments = DocumentsState & { available: boolean };


// hrc-031 (DEC-SCOPE-412 P4): `candidate` -- an external candidate reads the same card; they have no pool to join and no placement team.
export default function StudentCandidateDocumentsCard({ candidate = false }: { candidate?: boolean }) {
  const team = candidate ? "recruitment team" : "placement team";
  const [state, setState] = useState<MyDocuments | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const load = useCallback(() => {
    setLoadFailed(false);
    fetch(MY_DOCUMENTS_URL, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status));
        setState(await response.json());
      })
      .catch(() => setLoadFailed(true));
  }, []);
  useEffect(load, [load]);

  return (
    <section aria-labelledby="my-docs-heading" className="action-card" style={{ display: "grid", gap: 12 }}>
      <h3 id="my-docs-heading" style={{ margin: 0 }}>{candidate ? "Your documents" : "Documents for placement"}</h3>
      {loadFailed ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>
          Couldn&apos;t load your documents. <button type="button" className="btn secondary small" onClick={load}>Try again</button>
        </p>
      ) : !state ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading your documents…</p>
      ) : !state.available ? (
        <p className="muted" style={{ margin: 0 }}>
          <span>{candidate ? "Your documents aren't available right now. Please contact your recruiter." : "Join the placement candidate pool to share documents with the placement team."}</span>{" "}
          <button type="button" className="btn secondary small" onClick={load}>Refresh</button>
        </p>
      ) : (
        <>
          <h4 style={{ margin: 0 }}>Requested from you</h4>
          {documentCompletion(state.requests) && <p className="muted" style={{ margin: 0 }}>{documentCompletion(state.requests)}</p>}
          {state.requests.length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>Nothing has been requested from you.</p>
          ) : (
            <ul aria-label={`Documents the ${team} asked for`} style={{ margin: 0, paddingLeft: 0, listStyle: "none", display: "grid", gap: 8 }}>
              {state.requests.map((r) => (
                <li key={r.id} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
                  <span style={{ fontWeight: 600 }}>{documentTypeLabel(r.document_type)}</span>
                  <span className="badge">{REQUEST_STATUS_LABELS[r.status]}</span>
                  {r.note && <span style={{ overflowWrap: "anywhere" }}>{r.note}</span>}
                  {r.due_date && <span className="muted" style={{ fontSize: 13 }}>Due {r.due_date}</span>}
                </li>
              ))}
            </ul>
          )}
          <h4 style={{ margin: 0 }}>Your documents</h4>
          {state.documents.length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>You haven&apos;t uploaded any documents yet.</p>
          ) : (
            <ul aria-label="Your documents" style={{ margin: 0, paddingLeft: 0, listStyle: "none", display: "grid", gap: 8 }}>
              {state.documents.map((d) => (
                <li key={d.id} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
                  <span style={{ fontWeight: 600, overflowWrap: "anywhere" }}>{documentName(d)}</span>
                  <span className="muted" style={{ fontSize: 13, overflowWrap: "anywhere" }}>
                    {d.file_name ? `${d.file_name} · ` : ""}{fileSize(d.size_bytes)} · <LocalTime value={d.created_at} /> ·{" "}
                    {d.uploaded_by === "you" ? "Uploaded by you" : `Added by the ${team}`}
                  </span>
                  <DocumentFileActions linkUrl={`${MY_DOCUMENTS_URL}/${encodeURIComponent(d.id)}/link`} contentType={d.content_type} label={documentName(d)} />
                </li>
              ))}
            </ul>
          )}
          <CandidateDocumentUploadForm url={MY_DOCUMENTS_URL} idPrefix="my-doc" requests={state.requests} onUploaded={load} />
        </>
      )}
    </section>
  );
}

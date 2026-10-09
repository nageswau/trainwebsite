"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson, sendRequest, type SendOutcome } from "@/lib/apiErrors";
import { fileSize } from "@/lib/recruiterCandidates";
import {
  COMMISSION_KIND,
  DOCUMENT_ACCEPT,
  DOCUMENT_KINDS,
  DOCUMENT_MAX_BYTES,
  DOCUMENT_TYPES_TEXT,
  documentFileUrl,
  documentsUrl,
  documentUrl,
  type DocumentVersion,
  kindLabel,
  SHAREABLE_BY_DEFAULT,
  type UniversityDocument,
} from "@/lib/universityDocuments";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// upc-026 (§28): "everything related to that university in one place". Each document is a card (it reads well on a phone, like the
// contacts above it) with its current file, its earlier versions and -- with `canManage` -- a new version or an edit of its title and
// sharing. Every success re-reads the page (router.refresh). Titles and file names are data only.
const SAVE_FAILED = "The change could not be saved. Try again.";
const TOO_BIG = "The file must be at most 20 MB.";

function VersionLine({ v }: { v: DocumentVersion }) {
  return (
    <>
      {v.file_name ?? "File"} · {fileSize(v.size_bytes)} · uploaded by {v.uploaded_by.full_name}{v.uploaded_by.active ? "" : " (inactive)"} on{" "}
      <LocalTime value={v.uploaded_at} />
    </>
  );
}

function ShareableBox({ id, kind, checked, onChange }: { id: string; kind: string; checked: boolean; onChange: (value: boolean) => void }) {
  const commission = kind === COMMISSION_KIND;
  return (
    <div>
      <label htmlFor={id} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
        <input id={id} type="checkbox" checked={!commission && checked} disabled={commission} onChange={(e) => onChange(e.target.checked)}
          aria-describedby={commission ? `${id}-hint` : undefined} />
        Visible to counsellors (shareable)
      </label>
      {commission && <p className="muted" id={`${id}-hint`} style={{ margin: "4px 0 0", fontSize: 13 }}>A commission agreement is always internal.</p>}
    </div>
  );
}

/** The chosen file, or an error sentence before anything is sent. */
function pickedFile(input: HTMLInputElement | null): File | string {
  const file = input?.files?.[0];
  if (!file) return "Choose a file first.";
  if (file.size > DOCUMENT_MAX_BYTES) return TOO_BIG;
  return file;
}

function UploadForm({ busy, onSend, onCancel }: { busy: boolean; onSend: (form: FormData) => void; onCancel: () => void }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState("");
  const [title, setTitle] = useState("");
  const [shareable, setShareable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const file = pickedFile(fileInput.current);
    if (!kind) return setError("Choose the kind of document.");
    if (title.trim().length < 2) return setError("Enter a title of 2-200 characters.");
    if (typeof file === "string") return setError(file);
    setError(null);
    const form = new FormData();
    form.append("kind", kind);
    form.append("title", title.trim());
    form.append("shareable", String(kind !== COMMISSION_KIND && shareable));
    form.append("file", file);
    onSend(form);
  };
  return (
    <form onSubmit={submit} aria-label="Upload a document" aria-busy={busy} style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        <div className="field">
          <label htmlFor="doc-new-kind">Kind (required)</label>
          <select id="doc-new-kind" value={kind} autoFocus onChange={(e) => { setKind(e.target.value); setShareable(SHAREABLE_BY_DEFAULT.has(e.target.value)); }}>
            <option value="">Choose a kind</option>
            {Object.entries(DOCUMENT_KINDS).map(([key, word]) => <option key={key} value={key}>{word}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="doc-new-title">Title (required)</label>
          <input id="doc-new-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder="Fee structure 2026-27" />
        </div>
        <div className="field">
          <label htmlFor="doc-new-file">File (required)</label>
          <input id="doc-new-file" ref={fileInput} type="file" accept={DOCUMENT_ACCEPT} aria-describedby="doc-new-file-hint" />
          <p className="muted" id="doc-new-file-hint" style={{ margin: "4px 0 0", fontSize: 13 }}>{DOCUMENT_TYPES_TEXT}.</p>
        </div>
      </div>
      <ShareableBox id="doc-new-shareable" kind={kind} checked={shareable} onChange={setShareable} />
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Uploading…" : "Upload document"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}

function VersionForm({ d, busy, onSend, onCancel }: { d: UniversityDocument; busy: boolean; onSend: (form: FormData) => void; onCancel: () => void }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const id = `doc-${d.id}-file`;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const file = pickedFile(fileInput.current);
    if (typeof file === "string") return setError(file);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    onSend(form);
  };
  return (
    <form onSubmit={submit} aria-label={`New version of ${d.title}`} aria-busy={busy} style={{ display: "grid", gap: 8, marginTop: 8 }}>
      <div className="field" style={{ marginBottom: 0 }}>
        <label htmlFor={id}>New file (saves version {d.current_version + 1})</label>
        <input id={id} ref={fileInput} type="file" accept={DOCUMENT_ACCEPT} autoFocus aria-describedby={`${id}-hint`} />
        <p className="muted" id={`${id}-hint`} style={{ margin: "4px 0 0", fontSize: 13 }}>{DOCUMENT_TYPES_TEXT}.</p>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Uploading…" : "Upload version"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}

function EditForm({ d, busy, onSave, onCancel }: { d: UniversityDocument; busy: boolean; onSave: (body: Record<string, unknown>) => void; onCancel: () => void }) {
  const [title, setTitle] = useState(d.title);
  const [shareable, setShareable] = useState(d.shareable);
  const [error, setError] = useState<string | null>(null);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (title.trim().length < 2) return setError("Enter a title of 2-200 characters.");
    setError(null);
    const body: Record<string, unknown> = {};
    if (title.trim() !== d.title) body.title = title.trim();
    if (shareable !== d.shareable) body.shareable = shareable;
    onSave(body);
  };
  return (
    <form onSubmit={submit} aria-label={`Edit ${d.title}`} aria-busy={busy} style={{ display: "grid", gap: 8, marginTop: 8 }}>
      <div className="field" style={{ marginBottom: 0 }}>
        <label htmlFor={`doc-${d.id}-title`}>Title (required)</label>
        <input id={`doc-${d.id}-title`} value={title} maxLength={200} autoFocus onChange={(e) => setTitle(e.target.value)} />
      </div>
      <ShareableBox id={`doc-${d.id}-shareable`} kind={d.kind} checked={shareable} onChange={setShareable} />
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}

function DocumentCard({ d }: { d: UniversityDocument }) {
  const [current, ...earlier] = d.versions;
  return (
    <>
      <p style={{ margin: 0, fontWeight: 800, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", overflowWrap: "anywhere" }}>
        {d.title}
        <span className="badge">{kindLabel(d.kind)}</span>
        <span className="badge">Version {d.current_version}</span>
        <span className="badge">{d.shareable ? "Shareable" : "Internal"}</span>
      </p>
      {current && <p className="muted" style={{ margin: 0, overflowWrap: "anywhere" }}><VersionLine v={current} /></p>}
      {earlier.length > 0 && (
        <details>
          <summary>Earlier versions ({earlier.length})</summary>
          <ul className="list-clean" style={{ marginTop: 6 }}>
            {earlier.map((v) => (
              <li key={v.version} style={{ overflowWrap: "anywhere" }}>
                <a href={documentFileUrl(d, v.version)} download>Version {v.version}<span className="visually-hidden"> of {d.title}</span></a> · <VersionLine v={v} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

export default function UniversityDocuments({ universityId, documents, canManage }: { universityId: string; documents: UniversityDocument[]; canManage: boolean }) {
  const router = useRouter();
  const sending = useRef(false);
  const [open, setOpen] = useState<string | null>(null); // "new", "<id>:version", "<id>:edit", or null
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const addId = `uni-${universityId}-add-document`;

  async function run(request: () => Promise<SendOutcome>, done: string) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    const outcome = await request();
    sending.current = false;
    setBusy(false);
    if (outcome.ok) {
      setOpen(null);
      setNotice(done);
      focus(addId); // the control that had focus is gone
      router.refresh();
      return;
    }
    // A response without a readable detail (e.g. a 500) gets a plain sentence; a dropped request keeps the shared NOT_COMPLETED text.
    setFailure(outcome.status !== undefined && outcome.detail === undefined ? SAVE_FAILED : outcome.message);
  }
  const show = (key: string | null) => {
    setOpen(key);
    setFailure(null);
  };

  return (
    <section className="action-card wide" aria-labelledby="uni-documents">
      <h3 id="uni-documents">Documents</h3>
      {documents.length === 0 && open !== "new" && <p className="muted">No documents uploaded yet.</p>}
      {documents.length > 0 && (
        <ul aria-label="Documents" style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
          {documents.map((d) => (
            <li key={d.id} className="card" style={{ padding: 14, display: "grid", gap: 4 }}>
              <DocumentCard d={d} />
              <div className="actions" style={{ marginTop: 8 }}>
                <a className="btn secondary small" href={documentFileUrl(d)} download>Download<span className="visually-hidden"> {d.title}</span></a>
                {canManage && (
                  <>
                    <button type="button" className="btn secondary small" onClick={() => show(`${d.id}:version`)} disabled={busy}>
                      New version<span className="visually-hidden"> of {d.title}</span>
                    </button>
                    <button type="button" className="btn secondary small" onClick={() => show(`${d.id}:edit`)} disabled={busy}>
                      Edit<span className="visually-hidden"> {d.title}</span>
                    </button>
                  </>
                )}
              </div>
              {open === `${d.id}:version` && (
                <VersionForm d={d} busy={busy} onCancel={() => show(null)}
                  onSend={(form) => void run(() => sendRequest(documentUrl(universityId, d.id, "/versions"), { method: "POST", body: form }), `Version ${d.current_version + 1} uploaded.`)} />
              )}
              {open === `${d.id}:edit` && (
                <EditForm d={d} busy={busy} onCancel={() => show(null)}
                  onSave={(body) => void run(() => sendJson(documentUrl(universityId, d.id), "PATCH", body), "Document updated.")} />
              )}
            </li>
          ))}
        </ul>
      )}
      {canManage && (open === "new" ? (
        <div className="card" style={{ padding: 14, marginTop: 12 }}>
          <UploadForm busy={busy} onCancel={() => show(null)}
            onSend={(form) => void run(() => sendRequest(documentsUrl(universityId), { method: "POST", body: form }), "Document uploaded.")} />
        </div>
      ) : (
        <div style={{ marginTop: 12 }}>
          <button id={addId} type="button" className="btn secondary small" onClick={() => show("new")} disabled={busy}>Upload document</button>
        </div>
      ))}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {notice && <p className="muted" role="status">{notice}</p>}
    </section>
  );
}

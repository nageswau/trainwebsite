"use client";

import { useRef, useState } from "react";

import { fetchLink, isImage, type LinkMode } from "@/lib/candidateDocuments";

// hrc-015 (DEC-SCOPE-379 D3/D4): Preview and Download for one resume version or candidate document. Each click asks the API for a fresh
// 300-second signed link (audited there), so nothing long-lived sits in the page. A PDF (or a DOC/DOCX's converted PDF) opens in a frame,
// an image inline; "being prepared" (409) offers Check again, "no preview" (422) leaves Download.
type Props = { linkUrl: string; contentType: string; label: string };
type Preview = { url: string } | { pending: string } | null;

export default function DocumentFileActions({ linkUrl, contentType, label }: Props) {
  const [preview, setPreview] = useState<Preview>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);

  async function open(mode: LinkMode) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setError(null);
    const outcome = await fetchLink(linkUrl, mode);
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) {
      if (mode === "preview" && outcome.status === 409) return setPreview({ pending: outcome.message });
      setPreview(null);
      return setError(outcome.message);
    }
    if (mode === "download") return window.location.assign(outcome.url);
    setPreview({ url: outcome.url });
  }

  const title = `Preview of ${label}`;
  return (
    <>
      <span style={{ display: "inline-flex", gap: 6 }}>
        <button type="button" className="btn secondary small" disabled={busy} aria-label={`Preview ${label}`} onClick={() => void open("preview")}>Preview</button>
        <button type="button" className="btn secondary small" disabled={busy} aria-label={`Download ${label}`} onClick={() => void open("download")}>Download</button>
      </span>
      {error && <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13, flexBasis: "100%" }}>{error}</p>}
      {preview && (
        <div style={{ flexBasis: "100%", display: "grid", gap: 8 }}>
          {"pending" in preview ? (
            <p className="muted" role="status" style={{ margin: 0, fontSize: 13 }}>
              {preview.pending}{" "}
              <button type="button" className="btn secondary small" disabled={busy} onClick={() => void open("preview")}>Check again</button>
            </p>
          ) : isImage(contentType) ? (
            // eslint-disable-next-line @next/next/no-img-element -- a short-lived signed link, not an optimisable static asset
            <img src={preview.url} alt={title} style={{ maxWidth: "100%", maxHeight: "70vh", objectFit: "contain", border: "1px solid var(--line, #ddd)", borderRadius: 8 }} />
          ) : (
            <iframe src={preview.url} title={title} style={{ width: "100%", height: "min(70vh, 720px)", border: "1px solid var(--line, #ddd)", borderRadius: 8 }} />
          )}
          <div>
            <button type="button" className="btn secondary small" onClick={() => setPreview(null)}>Close preview</button>
          </div>
        </div>
      )}
    </>
  );
}

"use client";

import { useEffect, useId, useState } from "react";

import type { ProgramSyllabus, SyllabusModule } from "@/lib/types";

type Media = { id: string; slug: string; title: string; image_url: string | null; syllabus: ProgramSyllabus | null };
type Source = "none" | "manual" | "link" | "pdf";
type DraftModule = { title: string; topics: string };

const SOURCE_LABELS: Record<Source, string> = { none: "No syllabus (show the curriculum list)", manual: "Type modules and topics", link: "Google Drive or web link", pdf: "Upload a PDF" };

function detailMessage(detail: unknown, fallback: string) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return fallback;
}

const toDraft = (modules: SyllabusModule[]): DraftModule[] => modules.map((m) => ({ title: m.title, topics: m.topics.join("\n") }));
const EMPTY_MODULE: DraftModule = { title: "", topics: "" };

// PUB-025 (DEC-SCOPE-334): a course's card image (S3) and its ONE syllabus source (S1) -- typed modules, a Drive/web link, or a PDF.
export default function ProgramMediaEditor({ programId, programTitle, onClose }: { programId: string; programTitle: string; onClose: () => void }) {
  const id = useId();
  const [media, setMedia] = useState<Media | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const [source, setSource] = useState<Source>("none");
  const [modules, setModules] = useState<DraftModule[]>([{ ...EMPTY_MODULE }]);
  const [link, setLink] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [pdfFile, setPdfFile] = useState<File | null>(null);

  function load(next: Media) {
    setMedia(next);
    const s = next.syllabus;
    setSource(s ? s.source : "none");
    setModules(s?.source === "manual" && s.modules.length ? toDraft(s.modules) : [{ ...EMPTY_MODULE }]);
    setLink(s?.source === "link" ? s.url : "");
  }

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch(`/api/v1/admin/programs/${programId}/media`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error("load failed"))))
      .then(load)
      .catch((error) => { if (error?.name !== "AbortError") setFailed(true); });
    return () => controller.abort();
  }, [programId, version]);

  async function send(url: string, init: RequestInit, success: string, fallback: string) {
    setBusy(true);
    setNotice(null);
    try {
      const response = await fetch(url, init);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setNotice({ text: detailMessage(data.detail, fallback), failed: true });
        return false;
      }
      load(data as Media);
      setNotice({ text: success, failed: false });
      return true;
    } catch {
      setNotice({ text: fallback, failed: true });
      return false;
    } finally {
      setBusy(false);
    }
  }

  function upload(path: string, file: File, success: string, fallback: string) {
    const body = new FormData();
    body.append("file", file);
    return send(`/api/v1/admin/programs/${programId}/${path}`, { method: "PUT", body }, success, fallback);
  }

  async function saveSyllabus() {
    if (source === "pdf") {
      if (!pdfFile) return setNotice({ text: "Choose a PDF file first.", failed: true });
      if (await upload("syllabus/pdf", pdfFile, "Syllabus PDF uploaded.", "Unable to upload the PDF.")) setPdfFile(null);
      return;
    }
    const payload =
      source === "manual" ? { source, modules: modules.map((m) => ({ title: m.title, topics: m.topics.split("\n") })) }
      : source === "link" ? { source, url: link }
      : { source: null };
    await send(`/api/v1/admin/programs/${programId}/syllabus`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
      source === "none" ? "Syllabus removed." : "Syllabus saved.", "Unable to save the syllabus.");
  }

  async function uploadImage() {
    if (!imageFile) return setNotice({ text: "Choose an image file first.", failed: true });
    if (await upload("image", imageFile, "Card image uploaded.", "Unable to upload the image.")) setImageFile(null);
  }

  const updateModule = (index: number, patch: Partial<DraftModule>) => setModules((prev) => prev.map((m, i) => (i === index ? { ...m, ...patch } : m)));
  const current = media?.syllabus;

  return (
    <section className="action-card" aria-labelledby={`${id}-heading`} style={{ display: "grid", gap: 14 }}>
      <h4 id={`${id}-heading`} style={{ margin: 0 }}>Image and syllabus for {programTitle}</h4>
      {failed ? (
        <div>
          <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the course&apos;s image and syllabus.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((n) => n + 1)}>Retry</button>
        </div>
      ) : media === null ? (
        <p className="muted" role="status" style={{ fontSize: 13, margin: 0 }}>Loading…</p>
      ) : (
        <>
          <fieldset style={{ border: "1px solid var(--line)", borderRadius: 12, padding: 14, display: "grid", gap: 10, minWidth: 0 }}>
            <legend style={{ fontWeight: 800, padding: "0 6px" }}>Card image</legend>
            {media.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element -- admin preview of the API-served image
              <img src={media.image_url} alt={`Current card image for ${programTitle}`} style={{ width: 240, maxWidth: "100%", height: 135, objectFit: "cover", borderRadius: 10 }} />
            ) : (
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>No image. The course card shows its generated tile.</p>
            )}
            <div className="field">
              <label htmlFor={`${id}-image`}>PNG, JPEG or WebP, up to 2 MB, at least 120 × 120 px (16:9 looks best)</label>
              <input id={`${id}-image`} type="file" accept="image/png,image/jpeg,image/webp" disabled={busy}
                onChange={(event) => setImageFile(event.target.files?.[0] ?? null)} />
            </div>
            <div className="actions">
              <button type="button" className="btn small" disabled={busy || !imageFile} onClick={() => void uploadImage()}>{media.image_url ? "Replace image" : "Upload image"}</button>
              {media.image_url && (
                <button type="button" className="btn secondary small" disabled={busy}
                  onClick={() => void send(`/api/v1/admin/programs/${programId}/image`, { method: "DELETE" }, "Card image removed.", "Unable to remove the image.")}>
                  Remove image
                </button>
              )}
            </div>
          </fieldset>

          <fieldset style={{ border: "1px solid var(--line)", borderRadius: 12, padding: 14, display: "grid", gap: 10, minWidth: 0 }}>
            <legend style={{ fontWeight: 800, padding: "0 6px" }}>Syllabus</legend>
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>
              A course shows one syllabus. Saving a new one replaces the current one{current?.source === "pdf" ? " and deletes the uploaded PDF" : ""}.
              Visitors can open it without filling in a form.
            </p>
            <div role="radiogroup" aria-label="Syllabus source" style={{ display: "grid", gap: 6 }}>
              {(Object.keys(SOURCE_LABELS) as Source[]).map((key) => (
                <label key={key} style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 600 }}>
                  <input type="radio" name={`${id}-source`} value={key} checked={source === key} disabled={busy} onChange={() => setSource(key)} />
                  {SOURCE_LABELS[key]}
                </label>
              ))}
            </div>

            {source === "manual" && (
              <div style={{ display: "grid", gap: 12 }}>
                {modules.map((module, index) => (
                  <div key={index} style={{ display: "grid", gap: 6, borderLeft: "3px solid var(--line)", paddingLeft: 12 }}>
                    <div className="field">
                      <label htmlFor={`${id}-m${index}-title`}>Module {index + 1} title</label>
                      <input id={`${id}-m${index}-title`} value={module.title} maxLength={160} disabled={busy}
                        placeholder="e.g. Module 1: Python Basics" onChange={(event) => updateModule(index, { title: event.target.value })} />
                    </div>
                    <div className="field">
                      <label htmlFor={`${id}-m${index}-topics`}>Module {index + 1} topics (one per line)</label>
                      <textarea id={`${id}-m${index}-topics`} rows={4} value={module.topics} disabled={busy}
                        onChange={(event) => updateModule(index, { topics: event.target.value })} />
                    </div>
                    {modules.length > 1 && (
                      <button type="button" className="btn secondary small" style={{ justifySelf: "start" }} disabled={busy}
                        onClick={() => setModules((prev) => prev.filter((_, i) => i !== index))}>
                        Remove module {index + 1}
                      </button>
                    )}
                  </div>
                ))}
                <button type="button" className="btn secondary small" style={{ justifySelf: "start" }} disabled={busy || modules.length >= 40}
                  onClick={() => setModules((prev) => [...prev, { ...EMPTY_MODULE }])}>
                  Add module
                </button>
              </div>
            )}

            {source === "link" && (
              <div className="field">
                <label htmlFor={`${id}-link`}>Syllabus link (https://). For Google Drive, set sharing to &quot;Anyone with the link&quot;.</label>
                <input id={`${id}-link`} type="url" inputMode="url" maxLength={500} value={link} disabled={busy}
                  placeholder="https://drive.google.com/file/d/…/view" onChange={(event) => setLink(event.target.value)} />
              </div>
            )}

            {source === "pdf" && (
              <div style={{ display: "grid", gap: 6 }}>
                {current?.source === "pdf" && (
                  <a href={current.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--blue)", fontWeight: 700 }}>
                    View the current PDF<span className="visually-hidden"> (opens in a new tab)</span>
                  </a>
                )}
                <div className="field">
                  <label htmlFor={`${id}-pdf`}>{current?.source === "pdf" ? "Replace with another PDF" : "PDF file"}, up to 10 MB</label>
                  <input id={`${id}-pdf`} type="file" accept="application/pdf" disabled={busy} onChange={(event) => setPdfFile(event.target.files?.[0] ?? null)} />
                </div>
              </div>
            )}

            <div className="actions">
              <button type="button" className="btn small" disabled={busy || (source === "pdf" && !pdfFile)} onClick={() => void saveSyllabus()}>
                {busy ? "Saving…" : source === "pdf" ? "Upload PDF" : source === "none" ? "Save (no syllabus)" : "Save syllabus"}
              </button>
            </div>
          </fieldset>
        </>
      )}
      {notice && <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0 }}>{notice.text}</p>}
      <div className="actions">
        <button type="button" className="btn secondary small" onClick={onClose} disabled={busy}>Close</button>
      </div>
    </section>
  );
}

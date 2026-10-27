"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { formatSize } from "@/lib/agentDocuments";
import { uploadStoredFile } from "@/lib/uploadFile";

// nehn-027 (docs/superpowers/specs/2026-10-27-nehn-027-learning-material-files-design.md, DEC-SCOPE-294 M10): the trainer publishes a
// course material as an uploaded file (nehn-003 `learning_material` policy: PDF, Word, Excel, PowerPoint, JPG, PNG up to 20 MB) or as a
// link, then edits, reorders and deletes the batch's materials. Videos stay links (M3), so the file form offers no video type.

const API = "/api/v1/workflows/it/trainer/materials";
const MAX_BYTES = 20 * 1024 * 1024;
const EXTENSIONS = [".pdf", ".doc", ".docx", ".xlsx", ".pptx", ".jpg", ".jpeg", ".png"];
const LINK_GUIDANCE = "For videos, upload them to YouTube or Google Drive and add the link instead.";
const TYPES: Record<string, string> = { link: "Link", document: "Document", video: "Video", recording: "Provider recording", notes: "Notes" };
const FILE_TYPES = ["document", "notes"];

type Batch = { id: string; name: string; schedule: string };
type Material = { id: string; batch_id: string; title: string; resource_type: string; url: string; sort_order: number; file: { filename: string; size: number } | null };
type Mode = { id: string; action: "edit" | "delete" } | null;

function errorText(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(item => item?.msg || "Invalid input").join("; ");
  return "The change could not be saved.";
}

async function call(path: string, method: string, body?: unknown) {
  const response = await fetch(path, body === undefined ? { method } : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(errorText(data?.detail));
  return data;
}

/** Why the browser refuses `file` before uploading it, or null. The server checks the same policy (and the bytes) again. */
function fileProblem(file: File): string | null {
  if (!EXTENSIONS.some(ext => file.name.toLowerCase().endsWith(ext))) return `${file.name} is not a PDF, Word, Excel, PowerPoint, JPG or PNG file. ${LINK_GUIDANCE}`;
  if (file.size > MAX_BYTES) return `${file.name} is larger than 20 MB. ${LINK_GUIDANCE}`;
  return null;
}

export default function CourseMaterialsPanel({ batches }: { batches: Batch[] }) {
  const router = useRouter();
  const [materials, setMaterials] = useState<Material[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [shown, setShown] = useState("");
  const [source, setSource] = useState<"link" | "file">("link");
  const [mode, setMode] = useState<Mode>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const batch = shown || batches[0]?.id || "";
  const batchName = batches.find(item => item.id === batch)?.name || "this batch";
  const listed = (materials || []).filter(item => item.batch_id === batch);

  async function load() {
    try {
      setMaterials(await call(API, "GET"));
      setLoadError("");
    } catch (error) {
      setMaterials([]);
      setLoadError(error instanceof Error ? error.message : "Unable to load materials");
    }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => { if (message) feedbackRef.current?.focus(); }, [message]);

  async function run(work: () => Promise<unknown>, success: string) {
    setBusy(true);
    setMessage(null);
    try {
      await work();
      setMode(null);
      setMessage({ text: success, failed: false });
      await load();
      router.refresh();
      return true;
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : "The change could not be saved.", failed: true });
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function publish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const base = { batch_id: String(form.get("batch")), title: String(form.get("title")).trim(), resource_type: String(form.get("type")) };
    const file = (formElement.elements.namedItem("file") as HTMLInputElement | null)?.files?.[0];
    if (source === "file") {
      if (!file) return setMessage({ text: "Choose a file to upload.", failed: true });
      const problem = fileProblem(file);
      if (problem) return setMessage({ text: problem, failed: true });
    }
    const done = await run(async () => {
      const body = source === "file" ? { ...base, file_id: await uploadStoredFile(file as File, "learning_material") } : { ...base, url: String(form.get("url")).trim() };
      await call(API, "POST", body);
    }, "Material published.");
    if (done) {
      formElement.reset();
      setShown(base.batch_id);
    }
  }

  function move(index: number, by: -1 | 1) {
    const order = [...listed];
    [order[index], order[index + by]] = [order[index + by], order[index]];
    const changed = order.map((item, position) => ({ item, position })).filter(({ item, position }) => item.sort_order !== position);
    void run(async () => {
      for (const { item, position } of changed) await call(`${API}/${item.id}`, "PATCH", { sort_order: position });
    }, "Order saved.");
  }

  function edit(event: FormEvent<HTMLFormElement>, item: Material) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next: Record<string, string> = { title: String(form.get("title")).trim(), resource_type: String(form.get("type")) };
    if (!item.file) next.url = String(form.get("url")).trim();
    const changed = Object.fromEntries(Object.entries(next).filter(([key, value]) => value !== (key === "resource_type" ? item.resource_type : item[key as "title" | "url"])));
    if (!Object.keys(changed).length) return setMessage({ text: "Nothing was changed.", failed: true });
    void run(() => call(`${API}/${item.id}`, "PATCH", changed), "Material updated.");
  }

  // An older row may carry a type the picker no longer lists (the seed's "pdf"); it is offered as-is so saving never changes it (QA-02).
  const typeOptions = (types: string[], current?: string) =>
    (current && !types.includes(current) ? [current, ...types] : types).map(type => <option key={type} value={type}>{TYPES[type] || type}</option>);

  return <>
    <div className="action-card">
      <h3>Publish course material</h3>
      {message && (
        <div ref={feedbackRef} tabIndex={-1} className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} aria-live={message.failed ? "assertive" : "polite"}>
          {message.text}
        </div>
      )}
      <form className="form" aria-label="Publish course material" onSubmit={publish}>
        <div className="field"><label htmlFor="material-batch">Batch</label><select id="material-batch" name="batch" required><option value="">Select batch</option>{batches.map(item => <option key={item.id} value={item.id}>{item.name} · {item.schedule}</option>)}</select></div>
        <div className="field"><label htmlFor="material-title">Title</label><input id="material-title" name="title" minLength={2} maxLength={180} required /></div>
        <fieldset className="field full material-source">
          <legend>Material source</legend>
          <label><input type="radio" name="source" value="link" checked={source === "link"} onChange={() => setSource("link")} /> Add a link</label>
          <label><input type="radio" name="source" value="file" checked={source === "file"} onChange={() => setSource("file")} /> Upload a file</label>
        </fieldset>
        <div className="field"><label htmlFor="material-type">Material type</label><select id="material-type" name="type" key={source}>{typeOptions(source === "file" ? FILE_TYPES : Object.keys(TYPES))}</select></div>
        {source === "file" ? (
          <div className="field">
            <label htmlFor="material-file">File (PDF, Word, Excel, PowerPoint, JPG or PNG; up to 20 MB)</label>
            <input id="material-file" name="file" type="file" accept={EXTENSIONS.join(",")} required aria-describedby="material-file-hint" />
            <small id="material-file-hint" className="muted">{LINK_GUIDANCE}</small>
          </div>
        ) : (
          <div className="field"><label htmlFor="material-url">Resource URL</label><input id="material-url" name="url" type="url" maxLength={500} required /></div>
        )}
        <button className="btn" disabled={busy}>{busy ? "Saving…" : "Publish material"}</button>
      </form>
    </div>
    <div className="action-card">
      <h3>Your materials</h3>
      <div className="field"><label htmlFor="material-filter">Show batch</label><select id="material-filter" value={batch} onChange={event => { setShown(event.target.value); setMode(null); }}>{batches.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div>
      {materials === null && <p className="muted">Loading materials…</p>}
      {loadError && <p className="form-error" role="alert">{loadError}</p>}
      {materials !== null && !loadError && !listed.length && <p className="muted">{batches.length ? "No materials published for this batch yet." : "No batch is assigned to you yet."}</p>}
      {listed.length > 0 && (
        <ul className="material-list" aria-label={`Materials for ${batchName}`}>
          {listed.map((item, index) => {
            const open = mode?.id === item.id ? mode.action : null;
            const titleId = `material-${item.id}`;
            return (
              <li className="card" key={item.id} aria-labelledby={titleId}>
                <span className="badge">{TYPES[item.resource_type] || item.resource_type}</span>
                <h4 id={titleId}>{item.title}</h4>
                <p className="muted material-meta">{item.file ? `${item.file.filename} · ${formatSize(item.file.size)}` : item.url}</p>
                <div className="actions">
                  <a className="btn small secondary" href={item.url} {...(item.file ? {} : { target: "_blank", rel: "noopener noreferrer" })} aria-label={`Open ${item.title}`}>Open</a>
                  <button type="button" className="btn small ghost" disabled={busy || index === 0} onClick={() => move(index, -1)} aria-label={`Move ${item.title} up`}>↑</button>
                  <button type="button" className="btn small ghost" disabled={busy || index === listed.length - 1} onClick={() => move(index, 1)} aria-label={`Move ${item.title} down`}>↓</button>
                  <button type="button" className="btn small secondary" aria-expanded={open === "edit"} disabled={busy} onClick={() => { setMessage(null); setMode(open === "edit" ? null : { id: item.id, action: "edit" }); }} aria-label={`Edit ${item.title}`}>Edit</button>
                  <button type="button" className="btn small ghost" aria-expanded={open === "delete"} disabled={busy} onClick={() => { setMessage(null); setMode(open === "delete" ? null : { id: item.id, action: "delete" }); }} aria-label={`Delete ${item.title}`}>Delete</button>
                </div>
                {open === "edit" && (
                  <form className="form" aria-label={`Edit ${item.title}`} onSubmit={event => edit(event, item)}>
                    <div className="field"><label htmlFor={`${titleId}-title`}>Title</label><input id={`${titleId}-title`} name="title" defaultValue={item.title} minLength={2} maxLength={180} required /></div>
                    <div className="field"><label htmlFor={`${titleId}-type`}>Material type</label><select id={`${titleId}-type`} name="type" defaultValue={item.resource_type}>{typeOptions(item.file ? FILE_TYPES : Object.keys(TYPES), item.resource_type)}</select></div>
                    {!item.file && <div className="field full"><label htmlFor={`${titleId}-url`}>Resource URL</label><input id={`${titleId}-url`} name="url" type="url" defaultValue={item.url} maxLength={500} required /></div>}
                    <div className="actions">
                      <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button>
                      <button type="button" className="btn small ghost" onClick={() => setMode(null)}>Close</button>
                    </div>
                  </form>
                )}
                {open === "delete" && (
                  <div className="actions" role="group" aria-label={`Delete ${item.title}?`}>
                    <p className="muted" style={{ margin: 0 }}>Students of this batch will no longer see it.</p>
                    <button type="button" className="btn small" disabled={busy} onClick={() => void run(() => call(`${API}/${item.id}`, "DELETE"), "Material deleted. Students no longer see it.")}>Confirm delete</button>
                    <button type="button" className="btn small ghost" onClick={() => setMode(null)}>Keep</button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  </>;
}

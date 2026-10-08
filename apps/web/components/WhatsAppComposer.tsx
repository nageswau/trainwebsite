"use client";
import { useEffect, useId, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { BODY_MAX, isRenderedTemplate, missingNote, waHref, type ComposerTarget } from "@/lib/telecallerMessages";

/** tel-013 (spec §4; D3-D5, WA4): pick a template (rendered with the lead's values) or write a custom message, edit it, open wa.me, then
 *  confirm. Only "Yes, record as sent" writes the log -- wa.me can't report delivery, and "Not sent" keeps the text.
 *  rec-026: `target` names the endpoints -- a lead's (`leadTarget`) or a recruiter's contact / candidate (`recruiterTarget`). */
export default function WhatsAppComposer({ target, to, onRecorded, onCancel }: {
  target: ComposerTarget; to: string; onRecorded: () => void; onCancel: () => void;
}) {
  const [templates, setTemplates] = useState<{ id: string; name: string }[] | "failed" | null>(null);
  const [templateId, setTemplateId] = useState("");
  const [text, setText] = useState("");
  const [rendering, setRendering] = useState<"idle" | "loading" | "failed">("idle");
  const [mismatch, setMismatch] = useState(false);
  const [missing, setMissing] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const renderAbort = useRef<AbortController | null>(null);
  const recording = useRef(false); // QA-03: a second activation before the re-render must not record twice
  const picker = useRef<HTMLSelectElement>(null);
  const id = useId();

  const { loadTemplates } = target; // a module function, so the picker loads once
  useEffect(() => {
    picker.current?.focus(); // QA-02: the composer may open far from the button that opened it
    const controller = new AbortController();
    loadTemplates("whatsapp", controller.signal).then(setTemplates).catch(() => controller.signal.aborted || setTemplates("failed"));
    return () => {
      controller.abort();
      renderAbort.current?.abort();
    };
  }, [loadTemplates]);

  async function choose(next: string) {
    setTemplateId(next);
    setMismatch(false);
    setMissing([]);
    setConfirming(false);
    setError(null);
    renderAbort.current?.abort();
    if (!next) return setRendering("idle"); // a custom message keeps whatever was typed
    const controller = new AbortController();
    renderAbort.current = controller;
    setRendering("loading");
    try {
      const response = await fetch(target.renderUrl(next), { signal: controller.signal });
      const body = await response.json().catch(() => null);
      if (!response.ok || !isRenderedTemplate(body)) throw new Error("render failed");
      setText(body.body);
      setMismatch(body.product_mismatch === true);
      setMissing(body.missing ?? []);
      setRendering("idle");
    } catch {
      if (!controller.signal.aborted) setRendering("failed");
    }
  }

  async function record() {
    if (recording.current) return;
    recording.current = true;
    setBusy(true);
    setError(null);
    const outcome = await sendJson(target.createUrl, "POST", { ...target.payload, channel: "whatsapp", ...(templateId ? { template_id: templateId } : {}), body: text.trim() });
    recording.current = false;
    setBusy(false);
    if (outcome.ok) return onRecorded();
    setConfirming(false);
    setError(outcome.message);
  }

  const ready = text.trim() !== "" && rendering !== "loading";
  return (
    <div className="action-card" style={{ display: "grid", gap: 8, marginTop: 8 }} aria-label="WhatsApp message" role="group">
      <div className="field">
        <label htmlFor={`${id}-template`}>Template</label>
        <select ref={picker} id={`${id}-template`} value={templateId} disabled={busy} onChange={(e) => void choose(e.target.value)}>
          <option value="">Custom message</option>
          {Array.isArray(templates) && templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        {templates === "failed" && <p className="form-error" style={{ fontSize: 13 }}>Unable to load the templates. You can still write a custom message.</p>}
      </div>
      {rendering === "loading" && <p className="muted" role="status" style={{ fontSize: 13, margin: 0 }}>Preparing the message…</p>}
      {rendering === "failed" && <p className="form-error" role="alert" style={{ fontSize: 13, margin: 0 }}>Unable to load the template. Choose it again or write a custom message.</p>}
      {missing.length > 0 && <p className="form-warning" role="note" style={{ fontSize: 13, margin: 0 }}>{missingNote(missing)}</p>}
      {mismatch && (
        <p className="form-warning" role="note" style={{ fontSize: 13, margin: 0 }}>This template was made for another product. Check the text before sending.</p>
      )}
      <div className="field">
        <label htmlFor={`${id}-text`}>Message</label>
        <textarea id={`${id}-text`} rows={6} maxLength={BODY_MAX} value={text} disabled={busy} aria-describedby={`${id}-count`}
          onChange={(e) => { setText(e.target.value); setConfirming(false); }} />
        <span id={`${id}-count`} className="muted" style={{ fontSize: 12 }}>{text.length}/{BODY_MAX} characters</span>
      </div>
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      {confirming ? (
        <div role="group" aria-label="Confirm the send" className="actions">
          <span>Did you send it in WhatsApp?</span>
          <button type="button" className="btn small" disabled={busy} onClick={() => void record()}>{busy ? "Recording…" : "Yes, record as sent"}</button>
          <button type="button" className="btn secondary small" disabled={busy} onClick={() => setConfirming(false)}>Not sent</button>
        </div>
      ) : (
        <div className="actions">
          {ready && (
            <a className="btn small" href={waHref(to, text.trim())} target="_blank" rel="noopener noreferrer" onClick={() => { setConfirming(true); setError(null); }}>
              Open WhatsApp<span className="visually-hidden"> (opens in a new tab)</span>
            </a>
          )}
          <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
        </div>
      )}
    </div>
  );
}

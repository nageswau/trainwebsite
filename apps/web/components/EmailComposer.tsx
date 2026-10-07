"use client";
import { useEffect, useId, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import type { Template } from "@/lib/telecallerContent";
import { EMAIL_BODY_MAX, SUBJECT_MAX, activeTemplates, createMessageUrl, isRenderedTemplate, renderUrl } from "@/lib/telecallerMessages";

/** tel-014 (DEC-SCOPE-104, spec §5; EM4, E8): pick an email template (subject and body rendered with the lead's values) or write a custom
 *  email, edit both, and send. The API queues it and the worker delivers it to the lead's address; a refusal keeps what was typed. */
export default function EmailComposer({ leadId, onSent, onCancel }: { leadId: string; onSent: () => void; onCancel: () => void }) {
  const [templates, setTemplates] = useState<Template[] | "failed" | null>(null);
  const [templateId, setTemplateId] = useState("");
  const [subject, setSubject] = useState("");
  const [text, setText] = useState("");
  const [rendering, setRendering] = useState<"idle" | "loading" | "failed">("idle");
  const [mismatch, setMismatch] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const renderAbort = useRef<AbortController | null>(null);
  const sending = useRef(false); // a second activation before the re-render must not send twice
  const picker = useRef<HTMLSelectElement>(null);
  const id = useId();

  useEffect(() => {
    picker.current?.focus();
    const controller = new AbortController();
    activeTemplates("email", controller.signal).then(setTemplates).catch(() => controller.signal.aborted || setTemplates("failed"));
    return () => {
      controller.abort();
      renderAbort.current?.abort();
    };
  }, []);

  async function choose(next: string) {
    setTemplateId(next);
    setMismatch(false);
    setError(null);
    renderAbort.current?.abort();
    if (!next) return setRendering("idle"); // a custom email keeps whatever was typed
    const controller = new AbortController();
    renderAbort.current = controller;
    setRendering("loading");
    try {
      const response = await fetch(renderUrl(leadId, next), { signal: controller.signal });
      const body = await response.json().catch(() => null);
      if (!response.ok || !isRenderedTemplate(body)) throw new Error("render failed");
      setSubject(body.subject ?? "");
      setText(body.body);
      setMismatch(body.product_mismatch);
      setRendering("idle");
    } catch {
      if (!controller.signal.aborted) setRendering("failed");
    }
  }

  async function send() {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setError(null);
    const outcome = await sendJson(createMessageUrl(leadId), "POST",
      { channel: "email", ...(templateId ? { template_id: templateId } : {}), subject: subject.trim(), body: text.trim() });
    sending.current = false;
    setBusy(false);
    if (outcome.ok) return onSent();
    setError(outcome.message);
  }

  const ready = subject.trim() !== "" && text.trim() !== "" && rendering !== "loading" && !busy;
  return (
    <form className="action-card" style={{ display: "grid", gap: 8, marginTop: 8 }} aria-label="Email message"
      onSubmit={(e) => { e.preventDefault(); if (ready) void send(); }}>
      <div className="field">
        <label htmlFor={`${id}-template`}>Template</label>
        <select ref={picker} id={`${id}-template`} value={templateId} disabled={busy} onChange={(e) => void choose(e.target.value)}>
          <option value="">Custom message</option>
          {Array.isArray(templates) && templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        {templates === "failed" && <p className="form-error" style={{ fontSize: 13 }}>Unable to load the templates. You can still write a custom email.</p>}
      </div>
      {rendering === "loading" && <p className="muted" role="status" style={{ fontSize: 13, margin: 0 }}>Preparing the email…</p>}
      {rendering === "failed" && <p className="form-error" role="alert" style={{ fontSize: 13, margin: 0 }}>Unable to load the template. Choose it again or write a custom email.</p>}
      {mismatch && (
        <p className="form-warning" role="note" style={{ fontSize: 13, margin: 0 }}>This template was made for another product. Check the text before sending.</p>
      )}
      <div className="field">
        <label htmlFor={`${id}-subject`}>Subject</label>
        <input id={`${id}-subject`} value={subject} maxLength={SUBJECT_MAX} disabled={busy} onChange={(e) => setSubject(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor={`${id}-text`}>Message</label>
        <textarea id={`${id}-text`} rows={8} maxLength={EMAIL_BODY_MAX} value={text} disabled={busy} aria-describedby={`${id}-count`}
          onChange={(e) => setText(e.target.value)} />
        <span id={`${id}-count`} className="muted" style={{ fontSize: 12 }}>{text.length}/{EMAIL_BODY_MAX} characters</span>
      </div>
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={!ready}>{busy ? "Sending…" : "Send email"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

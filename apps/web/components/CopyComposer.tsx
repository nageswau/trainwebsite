"use client";
import { useEffect, useId, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { COPIES_URL, type CopyChannel, type GovernedTemplate, type MessageContext, type Party, recruiterTarget, usableTemplates } from "@/lib/recruiterMessages";
import { missingNote } from "@/lib/telecallerMessages";

type Rendered = { body: string; steps: string[] | null; missing: string[] };
const NOUN: Record<CopyChannel, string> = { linkedin: "LinkedIn message", call: "calling script" };

/** pob-023 (DEC-SCOPE-408 G10/G11): LinkedIn and calling scripts have no send API. Pick an approved (or your own) template, read the
 *  preview rendered with the party's values, edit it, then copy it -- the copy is logged (ids only). Copy exists only once a preview is
 *  shown (human review). A calling script shows its numbered steps. */
export default function CopyComposer({ channel, party, context, onCopied, onCancel }: {
  channel: CopyChannel; party: Party; context?: MessageContext; onCopied: (text: string) => void; onCancel: () => void;
}) {
  const [templates, setTemplates] = useState<GovernedTemplate[] | "failed" | null>(null);
  const [templateId, setTemplateId] = useState("");
  const [preview, setPreview] = useState<Rendered | "loading" | "failed" | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const picker = useRef<HTMLSelectElement>(null);
  const copying = useRef(false);
  const id = useId();
  const target = recruiterTarget(party, context);

  useEffect(() => {
    picker.current?.focus();
    const controller = new AbortController();
    usableTemplates(channel, controller.signal).then(setTemplates).catch(() => controller.signal.aborted || setTemplates("failed"));
    return () => controller.abort();
  }, [channel]);

  const renderUrl = templateId ? target.renderUrl(templateId) : "";
  useEffect(() => {
    if (!renderUrl) return setPreview(null);
    const controller = new AbortController();
    setPreview("loading");
    setError(null);
    fetch(renderUrl, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body: Rendered) => { setPreview(body); setText(body.body); })
      .catch(() => controller.signal.aborted || setPreview("failed"));
    return () => controller.abort();
  }, [renderUrl]);

  const ready = typeof preview === "object" && preview !== null && text.trim() !== "";

  async function copy() {
    if (!ready || copying.current) return;
    copying.current = true;
    setBusy(true);
    setError(null);
    const steps = preview.steps ?? [];
    const clip = steps.length ? `${text.trim()}\n\n${steps.map((s, i) => `${i + 1}. ${s}`).join("\n")}` : text.trim();
    try {
      await navigator.clipboard.writeText(clip);
    } catch {
      copying.current = false;
      setBusy(false);
      return setError("Your browser blocked the clipboard. Select the text and copy it yourself.");
    }
    const outcome = await sendJson(COPIES_URL, "POST", { ...target.payload, channel, template_id: templateId });
    copying.current = false;
    setBusy(false);
    if (outcome.ok) return onCopied(`${NOUN[channel][0].toUpperCase()}${NOUN[channel].slice(1)} for ${party.name} copied and logged.`);
    setError(`Copied, but not logged: ${outcome.message}`);
  }

  return (
    <div className="action-card" style={{ display: "grid", gap: 8, marginTop: 8 }} role="group" aria-label={NOUN[channel]}>
      <div className="field">
        <label htmlFor={`${id}-template`}>Template</label>
        <select ref={picker} id={`${id}-template`} value={templateId} disabled={busy} onChange={(e) => setTemplateId(e.target.value)}>
          <option value="">Choose a template</option>
          {Array.isArray(templates) && templates.map((t) => <option key={t.id} value={t.id}>{t.name}{t.visibility === "personal" ? " (personal)" : ""}</option>)}
        </select>
        {templates === "failed" && <p className="form-error" style={{ fontSize: 13 }}>Unable to load the templates.</p>}
        {Array.isArray(templates) && templates.length === 0 && <p className="muted" style={{ fontSize: 13 }}>No approved {NOUN[channel]} templates yet.</p>}
      </div>
      {preview === "loading" && <p className="muted" role="status" style={{ fontSize: 13, margin: 0 }}>Preparing the preview…</p>}
      {preview === "failed" && <p className="form-error" role="alert" style={{ fontSize: 13, margin: 0 }}>Unable to load the template. Choose it again.</p>}
      {typeof preview === "object" && preview !== null && (
        <>
          {preview.missing.length > 0 && <p className="form-warning" role="note" style={{ fontSize: 13, margin: 0 }}>{missingNote(preview.missing)}</p>}
          <div className="field">
            <label htmlFor={`${id}-text`}>{channel === "call" ? "Opening (preview — edit before copying)" : "Message (preview — edit before copying)"}</label>
            <textarea id={`${id}-text`} rows={5} value={text} disabled={busy} onChange={(e) => setText(e.target.value)} />
          </div>
          {preview.steps && (
            <div>
              <strong id={`${id}-steps`}>Steps</strong>
              <ol aria-labelledby={`${id}-steps`} style={{ margin: "4px 0 0", paddingLeft: 20, display: "grid", gap: 4 }}>
                {preview.steps.map((step, i) => <li key={i} style={{ overflowWrap: "anywhere" }}>{step}</li>)}
              </ol>
            </div>
          )}
        </>
      )}
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      <div className="actions">
        {ready && <button type="button" className="btn small" disabled={busy} onClick={() => void copy()}>{busy ? "Copying…" : "Copy to clipboard"}</button>}
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

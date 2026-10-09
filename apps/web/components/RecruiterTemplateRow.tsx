"use client";
import { useState } from "react";

import { LibraryEditFooter, LibraryRowActions, useLibraryRow } from "@/components/TelecallerLibraryRow";
import { BODY_LIMIT, CHANNEL_LABEL, RECRUITER_LIBRARY, unknownPlaceholders, type Channel, type MessageTemplate, type TemplateLibrary } from "@/lib/recruiterMessages";

type Preview = { subject: string | null; body: string };
type PreviewState = { status: "loading" } | { status: "failed" } | { status: "ready"; preview: Preview };

const kindText = (library: TemplateLibrary, row: MessageTemplate) => library.kinds?.[row.channel].find((k) => k.key === row.kind)?.label ?? row.kind ?? "";

/** rec-026: the template fields of the create form and a row's edit form. Named inputs are read with FormData by the owner; the message is
 *  controlled so its length and unknown placeholders show as you type (the API decides -- MS2). upc-012: `library` names the endpoints,
 *  kinds (none for the partnership library) and placeholders. */
export function RecruiterTemplateFields({ idPrefix, channel, onChannel, initial, disabled, library = RECRUITER_LIBRARY }: {
  idPrefix: string; channel: Channel; onChannel?: (channel: Channel) => void; initial?: MessageTemplate; disabled?: boolean; library?: TemplateLibrary;
}) {
  const [body, setBody] = useState(initial?.body ?? "");
  const id = (name: string) => `${idPrefix}-${name}`;
  const unknown = unknownPlaceholders(body, library.placeholders);
  return (
    <>
      {onChannel ? (
        <div className="field">
          <label htmlFor={id("channel")}>Channel (required)</label>
          <select id={id("channel")} name="channel" value={channel} onChange={(e) => onChannel(e.target.value as Channel)} disabled={disabled}>
            <option value="whatsapp">WhatsApp</option><option value="email">Email</option>
          </select>
        </div>
      ) : (
        <div className="field"><span className="muted">Channel</span> <strong>{CHANNEL_LABEL[channel]} (cannot be changed)</strong></div>
      )}
      {library.kinds && (
        <div className="field">
          <label htmlFor={id("kind")}>Kind (required)</label>
          <select key={channel} id={id("kind")} name="kind" defaultValue={initial?.kind ?? library.kinds[channel][0].key} required disabled={disabled}>
            {library.kinds[channel].map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </select>
        </div>
      )}
      <div className="field"><label htmlFor={id("name")}>Template name (required)</label><input id={id("name")} name="name" defaultValue={initial?.name} required maxLength={160} autoFocus={!!initial} disabled={disabled} /></div>
      {channel === "email" && (
        <div className="field"><label htmlFor={id("subject")}>Subject (required)</label><input id={id("subject")} name="subject" defaultValue={initial?.subject ?? ""} required maxLength={200} disabled={disabled} /></div>
      )}
      <div className="field">
        <label htmlFor={id("body")}>Message (required)</label>
        <textarea id={id("body")} name="body" value={body} onChange={(e) => setBody(e.target.value)} required rows={channel === "email" ? 8 : 4} maxLength={BODY_LIMIT[channel]} aria-describedby={`${id("hint")} ${id("count")}`} disabled={disabled} />
        <p id={id("hint")} className="muted" style={{ fontSize: 13 }}>{library.placeholderHint}</p>
        <p id={id("count")} className="muted" style={{ fontSize: 13 }}>{body.length} / {BODY_LIMIT[channel]}</p>
        {unknown.length > 0 && <p className="form-warning" role="status">Unknown placeholder: {unknown.join(", ")}</p>}
      </div>
    </>
  );
}

/** The JSON both forms send; only email carries a subject, and only a library with kinds a kind. */
export function templateBody(form: FormData, channel: Channel, library: TemplateLibrary = RECRUITER_LIBRARY): Record<string, unknown> {
  const text = (name: string) => String(form.get(name) ?? "").trim();
  return {
    ...(library.kinds ? { kind: text("kind") } : {}), name: text("name"), body: String(form.get("body") ?? ""),
    ...(channel === "email" ? { subject: text("subject") } : {}),
  };
}

/** rec-026: one template -- inline edit (channel fixed), deactivate / reactivate, and a preview rendered by the API with sample values. */
export default function RecruiterTemplateRow({ row, onChanged, library = RECRUITER_LIBRARY }: { row: MessageTemplate; onChanged: (notice: string) => void; library?: TemplateLibrary }) {
  const state = useLibraryRow(library.url, "rtpl", row, onChanged);
  const { editing, busy, id, patch, close } = state;
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const columns = library.kinds ? 5 : 4;

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = templateBody(new FormData(event.currentTarget), row.channel, library);
    if (await patch(body, `Saved ${body.name}.`, id("error"))) {
      setPreview(null);
      close();
    }
  }

  async function togglePreview() {
    if (preview) return setPreview(null);
    setPreview({ status: "loading" });
    try {
      const response = await fetch(`${library.url}/${row.id}/preview`);
      if (!response.ok) throw new Error(String(response.status));
      setPreview({ status: "ready", preview: await response.json() });
    } catch {
      setPreview({ status: "failed" });
    }
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={columns}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <RecruiterTemplateFields idPrefix={id("f")} channel={row.channel} initial={row} disabled={busy} library={library} />
            <LibraryEditFooter state={state} />
          </form>
        </td>
      </tr>
    );
  }

  return (
    <>
      <tr>
        <td data-label="Name">{row.name}</td>
        <td data-label="Channel">{CHANNEL_LABEL[row.channel]}</td>
        {library.kinds && <td data-label="Kind">{kindText(library, row)}</td>}
        <td data-label="Status"><span className="badge">{row.active ? "Active" : "Inactive"}</span></td>
        <td data-label="Actions">
          <LibraryRowActions state={state} row={row} hint={library.deactivateHint}>
            <button type="button" className="btn secondary small" aria-label={`${preview ? "Hide preview of" : "Preview"} ${row.name}`} aria-expanded={!!preview} aria-controls={id("preview")} onClick={togglePreview} disabled={busy}>
              {preview ? "Hide preview" : "Preview"}
            </button>
          </LibraryRowActions>
        </td>
      </tr>
      {preview && (
        <tr id={id("preview")}>
          <td colSpan={columns}>
            {preview.status === "loading" ? <p className="muted" role="status">Loading preview…</p>
              : preview.status === "failed" ? <p className="form-error" role="alert">Unable to load the preview.</p>
              : (
                <div role="region" aria-label={`Preview of ${row.name}`} style={{ display: "grid", gap: 6 }}>
                  <p className="muted" style={{ fontSize: 13 }}>{library.sampleNote}</p>
                  {preview.preview.subject !== null && <p style={{ overflowWrap: "anywhere" }}><strong>Subject:</strong> {preview.preview.subject}</p>}
                  <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{preview.preview.body}</p>
                </div>
              )}
          </td>
        </tr>
      )}
    </>
  );
}

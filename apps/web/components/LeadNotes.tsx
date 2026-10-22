"use client";

import { type FormEvent, useId, useState } from "react";

import LeadTimeline from "@/components/LeadTimeline";
import { sendJson } from "@/lib/apiErrors";
import { NOTE_MAX, noteAuthor, noteEntry, type LeadNote } from "@/lib/leadNotes";

type Notice = { text: string; failed: boolean } | null;

/** ccrm-002 (DEC-SCOPE-242): a lead's notes -- add one (plain text, append-only) above the full list, newest first. `url` is the lead
 *  route's `/notes` (telecaller, counselor or admin: each in its own scope). `onAdded` lets the page re-read its activity timeline. */
export default function LeadNotes({ url, onAdded }: { url: string; onAdded?: () => void }) {
  const id = useId();
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [version, setVersion] = useState(0);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = body.trim();
    if (!text) return setNotice({ text: "Write a note first.", failed: true });
    setBusy(true);
    const outcome = await sendJson(url, "POST", { body: text });
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    setBody("");
    setNotice({ text: "Note added.", failed: false });
    setVersion((n) => n + 1);
    onAdded?.();
  }

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <form onSubmit={submit} noValidate style={{ display: "grid", gap: 6, maxWidth: "40rem" }}>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={`${id}-body`}>Add a note</label>
          <textarea id={`${id}-body`} rows={3} maxLength={NOTE_MAX} aria-describedby={`${id}-count`} value={body} disabled={busy}
            onChange={(e) => { setBody(e.target.value); setNotice(null); }} />
          <span id={`${id}-count`} className="muted" style={{ fontSize: 12, justifySelf: "end" }}>{body.length} / {NOTE_MAX}</span>
        </div>
        {notice && (
          <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} style={{ margin: 0, fontSize: 13 }}>{notice.text}</p>
        )}
        <div><button type="submit" className="btn small" disabled={busy}>{busy ? "Adding…" : "Add note"}</button></div>
      </form>
      <LeadTimeline<LeadNote> url={url} version={version} label="Lead notes" noun="notes" entryOf={noteEntry} actorOf={noteAuthor} />
    </div>
  );
}

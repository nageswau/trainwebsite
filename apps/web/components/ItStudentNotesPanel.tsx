"use client";

import { FormEvent, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { isPage, sendJson } from "@/lib/apiErrors";
import { authorRole, IT_NOTE_MAX, itNoteVisibilityUrl, itStudentNotesUrl, PAGE_SIZE, type ItStudentNote, type ItStudentNotes } from "@/lib/itStudentNotes";

type Message = { text: string; failed: boolean } | null;

// itc-028 (DEC-SCOPE-351): staff notes on an IT student. Newest first, append-only; every note starts internal and only its author or the IT
// Admin shares it with the student (after a confirm). The first page is read by the server page; older pages load on request. The entry
// is kept on any failure; a second submit while one is in flight is ignored.
export default function ItStudentNotesPanel({ initial }: { initial: ItStudentNotes }) {
  const url = itStudentNotesUrl(initial.student.id);
  const [items, setItems] = useState<ItStudentNote[]>(initial.items);
  const [total, setTotal] = useState(initial.total);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<Message>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [shareMessage, setShareMessage] = useState<Message>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreFailed, setMoreFailed] = useState(false);
  const inFlight = useRef(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    if (!body.trim()) {
      setMessage({ text: "Write a note first.", failed: true });
      return;
    }
    inFlight.current = true;
    setSending(true);
    setMessage(null);
    const outcome = await sendJson(url, "POST", { body });
    inFlight.current = false;
    setSending(false);
    if (!outcome.ok) {
      setMessage({ text: outcome.message, failed: true });
      return;
    }
    setItems((current) => [outcome.data as ItStudentNote, ...current]);
    setTotal((current) => current + 1);
    setBody("");
    setMessage({ text: "Note saved. Only staff can see it.", failed: false });
  }

  async function changeVisibility(note: ItStudentNote) {
    const share = note.visibility === "internal";
    const question = share
      ? `Share this note with ${initial.student.full_name}? They will see it in their Updates.`
      : `Stop sharing this note? ${initial.student.full_name} will no longer see it.`;
    if (busyId || !window.confirm(question)) return;
    setBusyId(note.id);
    setShareMessage(null);
    const outcome = await sendJson(itNoteVisibilityUrl(initial.student.id, note.id), "PUT", { visibility: share ? "student" : "internal" });
    setBusyId(null);
    if (!outcome.ok) {
      setShareMessage({ text: outcome.message, failed: true });
      return;
    }
    const updated = outcome.data as ItStudentNote;
    setItems((current) => current.map((n) => (n.id === updated.id ? { ...n, visibility: updated.visibility, shared_at: updated.shared_at } : n)));
    setShareMessage({ text: share ? "Shared with the student." : "The student no longer sees this note.", failed: false });
  }

  async function loadMore() {
    setLoadingMore(true);
    setMoreFailed(false);
    try {
      const response = await fetch(`${url}?limit=${PAGE_SIZE}&offset=${items.length}`);
      const data: unknown = response.ok ? await response.json() : null;
      if (!isPage<ItStudentNote>(data)) throw new Error("not a page");
      setItems((current) => [...current, ...data.items.filter((n) => !current.some((c) => c.id === n.id))]);
      setTotal(data.total);
    } catch {
      setMoreFailed(true);
    }
    setLoadingMore(false);
  }

  return (
    <>
      <form className="form action-card" onSubmit={submit} aria-label="Add a note">
        <div className="field">
          <label htmlFor="it-student-note-body">New note</label>
          <textarea id="it-student-note-body" rows={4} maxLength={IT_NOTE_MAX} value={body} onChange={(e) => setBody(e.target.value)} aria-describedby="it-student-note-help" />
          <span id="it-student-note-help" className="muted" style={{ fontSize: 13 }}>{body.length} / {IT_NOTE_MAX} · Saved as internal: only staff see it until it is shared.</span>
        </div>
        <div>
          <button className="btn" aria-busy={sending} disabled={sending}>{sending ? "Saving…" : "Save note"}</button>
        </div>
        <div className={message ? (message.failed ? "form-error" : "form-message") : undefined} role="status" aria-live="polite" style={message ? { marginTop: 8, overflowWrap: "anywhere" } : undefined}>
          {message?.text}
        </div>
      </form>

      <section className="action-card" aria-labelledby="it-student-notes-history">
        {/* QA-01: one grid child -- an empty status region must not add its own gap to the card */}
        <div>
          <h3 id="it-student-notes-history">Notes</h3>
          {total > 0 && <p className="muted" style={{ fontSize: 13 }}>{total === 1 ? "1 note" : `${total} notes`}</p>}
          <div className={shareMessage ? (shareMessage.failed ? "form-error" : "form-message") : undefined} role="status" aria-live="polite" style={shareMessage ? { overflowWrap: "anywhere" } : undefined}>
            {shareMessage?.text}
          </div>
        </div>
        {items.length === 0 ? (
          <p className="muted">No notes yet.</p>
        ) : (
          <ul style={{ paddingLeft: 0, listStyle: "none", margin: 0 }}>
            {items.map((n) => (
              <li key={n.id} style={{ padding: "10px 0", borderBottom: "1px solid var(--line, #e5e7eb)", overflowWrap: "anywhere" }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", alignItems: "center", fontSize: 13 }}>
                  <strong>{n.author_name}</strong>
                  <span className="badge">{authorRole(n.author_role)}</span>
                  <span className="muted"><LocalTime value={n.created_at} time /></span>
                  {n.visibility === "student" ? <span className="status">Shared with student</span> : <span className="status pending">Internal</span>}
                </div>
                <p style={{ margin: "6px 0 0", whiteSpace: "pre-wrap" }}>{n.body}</p>
                {n.can_change_visibility && (
                  <button type="button" className="btn small secondary" style={{ marginTop: 8 }} disabled={busyId !== null} aria-busy={busyId === n.id} onClick={() => changeVisibility(n)}>
                    {n.visibility === "internal" ? "Share with student" : "Stop sharing"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {moreFailed && <p className="form-error" role="alert">Unable to load older notes. Try again.</p>}
        {items.length < total && (
          <button type="button" className="btn secondary small" style={{ marginTop: 12 }} disabled={loadingMore} onClick={loadMore}>
            {loadingMore ? "Loading…" : "Load older notes"}
          </button>
        )}
      </section>
    </>
  );
}

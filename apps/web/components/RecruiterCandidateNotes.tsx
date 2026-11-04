"use client";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import { SAVE_FAILED, writeFailure } from "@/lib/bdmTasks";
import { isCandidateNote, newNoteUrl, NOTE_MAX, notesUrl, PRIVATE_HINT, type CandidateNote } from "@/lib/recruiterCandidateTasks";
import { getPage } from "@/lib/telecallerCatalogue";

/** hrc-016 (T2): a candidate's private notes, newest first. Readers see them; writers add one (append-only: no edit or delete). Loading,
 *  empty and error-with-Retry states; "Show older notes" pages. `onAdded` lets the page re-read the timeline. */
export default function RecruiterCandidateNotes({ candidateId, canAdd, onAdded }: { candidateId: string; canAdd: boolean; onAdded?: () => void }) {
  const id = useId();
  const [notes, setNotes] = useState<CandidateNote[] | null>(null);
  const [total, setTotal] = useState(0);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreFailed, setMoreFailed] = useState(false);
  const errorRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<CandidateNote>(notesUrl(candidateId), controller.signal)
      .then((page) => { setNotes(page.items); setTotal(page.total); })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [candidateId, version]);

  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);

  async function more() {
    if (!notes) return;
    setLoadingMore(true);
    setMoreFailed(false);
    const page = await getPage<CandidateNote>(notesUrl(candidateId, notes.length)).catch(() => null);
    setLoadingMore(false);
    if (page) { setNotes([...notes, ...page.items.filter((n) => !notes.some((m) => m.id === n.id))]); setTotal(page.total); } else setMoreFailed(true);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!body.trim()) return setError("Write a note first");
    setBusy(true);
    setError(null);
    const result = await sendJson(newNoteUrl(candidateId), "POST", { body });
    setBusy(false);
    if (!result.ok) return setError(writeFailure(result.status) === "retry" ? SAVE_FAILED : result.message);
    if (!isCandidateNote(result.data)) return setError(SAVE_FAILED);
    setBody("");
    setVersion((n) => n + 1);
    onAdded?.();
  }

  const headingId = `${id}-heading`;
  return (
    <section className="action-card" aria-labelledby={headingId} aria-busy={notes === null && !failed}>
      <h3 id={headingId} style={{ marginTop: 0 }}>Notes</h3>
      <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>{PRIVATE_HINT}</p>
      {canAdd && (
        <form aria-label="Add note" noValidate onSubmit={submit} style={{ display: "grid", gap: 4, marginBottom: 12 }}>
          <label htmlFor={`${id}-body`}>New note</label>
          <textarea id={`${id}-body`} rows={3} maxLength={NOTE_MAX} value={body} onChange={(e) => setBody(e.target.value)}
            aria-invalid={error ? true : undefined} aria-describedby={`${id}-count${error ? ` ${id}-error` : ""}`} />
          <p id={`${id}-count`} className="muted" style={{ margin: 0, fontSize: 13 }}>{body.length}/{NOTE_MAX}</p>
          {error && <p id={`${id}-error`} ref={errorRef} tabIndex={-1} className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
          <div className="actions"><button type="submit" className="btn small" disabled={busy}>{busy ? "Adding…" : "Add note"}</button></div>
        </form>
      )}
      {failed ? (
        <div>
          <p className="form-error" role="alert">Unable to load notes.</p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((n) => n + 1)}>Retry</button>
        </div>
      ) : notes === null ? (
        <p className="muted" role="status">Loading notes…</p>
      ) : notes.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No notes yet.</p>
      ) : (
        <>
          <ul aria-label="Candidate notes" style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
            {notes.map((note) => (
              <li key={note.id} style={{ borderTop: "1px solid var(--border, #e5e7eb)", paddingTop: 8 }}>
                <p style={{ margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{note.body}</p>
                <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
                  {note.author?.full_name ?? "Someone"} · <LocalTime value={note.created_at} time />
                </p>
              </li>
            ))}
          </ul>
          {notes.length < total && (
            <button type="button" className="btn secondary small" style={{ marginTop: 8 }} disabled={loadingMore} onClick={() => void more()}>
              {loadingMore ? "Loading…" : `Show older notes (${total - notes.length})`}
            </button>
          )}
          {moreFailed && <p className="form-error" role="alert">Unable to load older notes. Try again.</p>}
        </>
      )}
    </section>
  );
}

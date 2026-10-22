"use client";

import { FormEvent, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { isPage, sendJson } from "@/lib/apiErrors";
import { AUTHOR_ROLE, NOTE_MAX, studentNotesUrl, type StudentNote, type StudentNotes } from "@/lib/studentNotes";

// ccrm-010 (DEC-SCOPE-241): a student's internal notes -- the counselling history. Newest first, append-only (no edit or delete), never
// shown to the student or the agent. The first page is read by the server page; older pages load on request. The entry is kept on any
// failure so it can be sent again; a second submit while one is in flight is ignored.
export default function StudentNotesPanel({ initial }: { initial: StudentNotes }) {
  const url = studentNotesUrl(initial.student.id);
  const [items, setItems] = useState<StudentNote[]>(initial.items);
  const [total, setTotal] = useState(initial.total);
  const [body, setBody] = useState("");
  const [applicationId, setApplicationId] = useState("");
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
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
    const outcome = await sendJson(url, "POST", { body, application_id: applicationId || null });
    inFlight.current = false;
    setSending(false);
    if (!outcome.ok) {
      setMessage({ text: outcome.message, failed: true });
      return;
    }
    setItems((current) => [outcome.data as StudentNote, ...current]);
    setTotal((current) => current + 1);
    setBody("");
    setApplicationId("");
    setMessage({ text: "Note saved.", failed: false });
  }

  async function loadMore() {
    setLoadingMore(true);
    setMoreFailed(false);
    try {
      const response = await fetch(`${url}?limit=20&offset=${items.length}`);
      const data: unknown = response.ok ? await response.json() : null;
      if (!isPage<StudentNote>(data)) throw new Error("not a page");
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
          <label htmlFor="student-note-body">New note</label>
          <textarea id="student-note-body" rows={4} maxLength={NOTE_MAX} value={body} onChange={(e) => setBody(e.target.value)} aria-describedby="student-note-count" />
          <span id="student-note-count" className="muted" style={{ fontSize: 13 }}>{body.length} / {NOTE_MAX}</span>
        </div>
        {initial.applications.length > 0 && (
          <div className="field">
            <label htmlFor="student-note-application">About an application (optional)</label>
            <select id="student-note-application" value={applicationId} onChange={(e) => setApplicationId(e.target.value)}>
              <option value="">The student in general</option>
              {initial.applications.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
            </select>
          </div>
        )}
        <div>
          <button className="btn" aria-busy={sending}>{sending ? "Saving…" : "Save note"}</button>
        </div>
        <div className={message ? (message.failed ? "form-error" : "form-message") : undefined} role="status" aria-live="polite" style={message ? { marginTop: 8, overflowWrap: "anywhere" } : undefined}>
          {message?.text}
        </div>
      </form>

      <section className="action-card" aria-labelledby="student-notes-history">
        <h2 id="student-notes-history" style={{ fontSize: 18 }}>Counselling history</h2>
        {total > 0 && <p className="muted" style={{ fontSize: 13 }}>{total === 1 ? "1 note" : `${total} notes`}</p>}
        {items.length === 0 ? (
          <p className="muted">No notes yet.</p>
        ) : (
          <ul style={{ paddingLeft: 0, listStyle: "none", margin: 0 }}>
            {items.map((n) => (
              <li key={n.id} style={{ padding: "10px 0", borderBottom: "1px solid var(--line, #e5e7eb)", overflowWrap: "anywhere" }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", alignItems: "center", fontSize: 13 }}>
                  <strong>{n.author_name}</strong>
                  <span className="badge">{AUTHOR_ROLE[n.author_role] ?? n.author_role}</span>
                  <span className="muted"><LocalTime value={n.created_at} time /></span>
                  {n.application && <span className="muted">{n.application.label}</span>}
                </div>
                <p style={{ margin: "6px 0 0", whiteSpace: "pre-wrap" }}>{n.body}</p>
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

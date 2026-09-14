"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type ApplicationRow = { id: string; student_id: string; student: string };
type ConversationMessage = { id: string; sender_id: string; recipient_id: string; body: string; created_at: string };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "The operation could not be completed.";
}

// RAID.md I-19: the Counselor role had no way to see or reply to a student's message at
// all -- not even a nav entry existed. `POST`/`GET /communications/messages` already
// existed generically and needed no backend change; this adds the missing student
// picker (never a raw id typed by hand, same precedent as ADM-001-008/OVS-002/etc.) and
// wires the reply action to it.
export default function CounselorChatPanel({ userId }: { userId: string }) {
  const [students, setStudents] = useState<ApplicationRow[] | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [messages, setMessages] = useState<ConversationMessage[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch("/api/v1/portal/overseas/counselor/applications")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => setStudents(data.rows || []))
      .catch(() => setStudents([]));
  }, []);

  const uniqueStudents = useMemo(() => {
    const seen = new Set<string>();
    return (students || []).filter((row) => {
      if (seen.has(row.student_id)) return false;
      seen.add(row.student_id);
      return true;
    });
  }, [students]);

  function loadConversation(studentId: string) {
    setSelectedId(studentId);
    setMessages(null);
    if (!studentId) return;
    fetch(`/api/v1/communications/messages/${studentId}`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setMessages(data))
      .catch(() => setMessages([]));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage("");
    setFailed(false);
    const form = new FormData(formElement);
    try {
      const response = await fetch("/api/v1/communications/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recipient_id: selectedId, body: form.get("body"), context_type: "counselor_chat" }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(detailMessage(data.detail));
      setMessage("Reply sent.");
      formElement.reset();
      loadConversation(selectedId);
    } catch (error) {
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "Send failed");
    } finally {
      setBusy(false);
    }
  }

  if (students === null) {
    return (
      <div className="action-card">
        <h3>Reply to a student</h3>
        <p className="muted">Loading your assigned students…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Reply to a student</h3>
      <div className="field">
        <label htmlFor="counselor-chat-student">Student</label>
        <select id="counselor-chat-student" value={selectedId} onChange={(event) => loadConversation(event.target.value)}>
          <option value="">Select student</option>
          {uniqueStudents.map((row) => (
            <option key={row.student_id} value={row.student_id}>{row.student}</option>
          ))}
        </select>
      </div>
      {!uniqueStudents.length && <p className="muted">No students are assigned to you yet.</p>}
      {selectedId && (
        <>
          {messages === null ? (
            <p className="muted">Loading conversation…</p>
          ) : (
            <div className="qa-item">
              <div className="qa-item-head"><strong>Conversation</strong></div>
              {messages.length === 0 && <p className="muted answer-empty">No messages yet -- send the first one below.</p>}
              {messages.map((row) => (
                <p key={row.id} className={row.sender_id === userId ? "answer-text" : "muted"} style={{ margin: "6px 0" }}>
                  {row.sender_id === userId ? "You: " : "Student: "}{row.body}
                </p>
              ))}
            </div>
          )}
          <form className="form" onSubmit={submit}>
            <div className="field full">
              <label htmlFor="counselor-chat-reply">Reply</label>
              <textarea id="counselor-chat-reply" name="body" required />
            </div>
            {message && <div className={failed ? "form-error" : "form-message"} role="status" aria-live="polite">{message}</div>}
            <button className="btn small" disabled={busy}>{busy ? "Sending…" : "Send reply"}</button>
          </form>
        </>
      )}
    </div>
  );
}

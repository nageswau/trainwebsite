"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { staffFailure } from "@/lib/agentStaff";
import { isPage, sendJson, type Page } from "@/lib/apiErrors";

const URL = "/api/v1/counselor/students";
const PAGE_SIZE = 20;

type WalkInStudent = { id: string; full_name: string; email: string; phone: string | null; student_code: string | null; setup: "pending_setup" | "link_expired" | null };

const SETUP_LABEL = { pending_setup: "Set-up pending", link_expired: "Link expired" } as const;

// csc-002 (DEC-SCOPE-227): a student who walks into the office gets a login from their counselor. The student sets their own password
// from the emailed link (the counselor never sees it) and is in the counselor's caseload at once (csc-001), e.g. for Schedule appointment.
export default function CounselorWalkInStudents() {
  const [data, setData] = useState<Page<WalkInStudent> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [offset, setOffset] = useState(0);

  const load = useCallback((at: number) => {
    setLoadFailed(false);
    fetch(`${URL}?limit=${PAGE_SIZE}&offset=${at}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((body: unknown) => {
        if (!isPage<WalkInStudent>(body)) throw new Error("not a page");
        setData(body);
      })
      .catch(() => setLoadFailed(true));
  }, []);

  useEffect(() => {
    load(offset);
  }, [load, offset]);

  const reload = () => load(offset);

  return (
    <div className="action-card">
      <h3>Walk-in students</h3>
      <p className="muted" style={{ fontSize: 13 }}>Create a login for a student who came to the office. They receive an email to set their password, and they are added to your students.</p>
      {loadFailed ? (
        <>
          <p className="form-error" role="alert">Unable to load your walk-in students.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </>
      ) : data === null ? (
        <p className="muted" aria-busy="true">Loading your walk-in students…</p>
      ) : data.items.length === 0 ? (
        <p className="muted">No walk-in students yet. Add one below.</p>
      ) : (
        <ul style={{ paddingLeft: 0, listStyle: "none" }}>
          {data.items.map((s) => (
            <li key={s.id} style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", padding: "8px 0", borderBottom: "1px solid var(--line, #e5e7eb)", overflowWrap: "anywhere" }}>
              <strong>{s.full_name}</strong>
              <span>{s.email}</span>
              {s.student_code && <span className="muted">Student ID {s.student_code}</span>}
              <span className="badge">{s.setup ? SETUP_LABEL[s.setup] : "Active"}</span>
            </li>
          ))}
        </ul>
      )}
      {data !== null && data.total > PAGE_SIZE && (
        <nav aria-label="Walk-in student pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
          <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
          <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
        </nav>
      )}
      <AddWalkInStudentForm onCreated={reload} />
    </div>
  );
}

// The entry is kept on any failure so it can be corrected and sent again.
function AddWalkInStudentForm({ onCreated }: { onCreated: () => void }) {
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const inFlight = useRef(false);
  const messageRef = useRef<HTMLDivElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setSending(true);
    setMessage(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const phone = String(data.get("phone") ?? "").trim();
    const outcome = await sendJson(URL, "POST", { full_name: String(data.get("full_name") ?? ""), email: String(data.get("email") ?? ""), phone: phone || null });
    inFlight.current = false;
    setSending(false);
    if (!outcome.ok) {
      setMessage({ text: staffFailure(outcome, true), failed: true });
    } else {
      const { student, email_status } = outcome.data as { student: WalkInStudent; email_status: string };
      setMessage({
        text: email_status === "sent" ? `Account created for ${student.full_name}. A set-password link was emailed to ${student.email}.` : `Account created for ${student.full_name}, but the set-password email was not delivered.`,
        failed: false,
      });
      form.reset();
      onCreated();
    }
    messageRef.current?.focus();
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Add a walk-in student">
      <h4>Add a walk-in student</h4>
      <div className="field"><label htmlFor="walk-in-full-name">Full name</label><input id="walk-in-full-name" name="full_name" maxLength={160} required autoComplete="off" /></div>
      <div className="field"><label htmlFor="walk-in-email">Email</label><input id="walk-in-email" name="email" type="email" maxLength={255} required autoComplete="off" /></div>
      <div className="field"><label htmlFor="walk-in-phone">Phone (optional)</label><input id="walk-in-phone" name="phone" type="tel" maxLength={40} autoComplete="off" /></div>
      <button className="btn" disabled={sending}>{sending ? "Creating…" : "Create account"}</button>
      <div ref={messageRef} tabIndex={-1} className={message ? (message.failed ? "form-error" : "form-message") : undefined} role="status" aria-live="polite" style={message ? { marginTop: 8, overflowWrap: "anywhere" } : undefined}>
        {message?.text}
      </div>
    </form>
  );
}

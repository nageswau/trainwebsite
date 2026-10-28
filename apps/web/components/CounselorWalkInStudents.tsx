"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { staffFailure } from "@/lib/agentStaff";
import { isPage, sendJson, type Page } from "@/lib/apiErrors";

import CounselorWalkInStudentRow, { SOURCE_LABEL, WALK_IN_URL as URL, type WalkInStudent } from "./CounselorWalkInStudentRow";

const PAGE_SIZE = 20;

// csc-002 (DEC-SCOPE-227): a student who walks into the office gets a login from their counselor. The student sets their own password
// from the emailed link (the counselor never sees it) and is in the counselor's caseload at once (csc-001), e.g. for Schedule appointment.
// csc-003 (DEC-SCOPE-228): each pending row can resend the link or fix the details (CounselorWalkInStudentRow).
// ccrm-043 (DEC-SCOPE-317): the list is all the counselor's students (walk-ins and the students of their applications), filtered by
// source at once and by the search on submit; a filter change returns to the first page.
export default function CounselorWalkInStudents() {
  const [data, setData] = useState<Page<WalkInStudent> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [offset, setOffset] = useState(0);
  const [source, setSource] = useState("");
  const [q, setQ] = useState("");
  const [typed, setTyped] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const filtered = source !== "" || q !== "";

  const load = useCallback((at: number, bySource: string, text: string) => {
    setLoadFailed(false);
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(at) });
    if (bySource) params.set("source", bySource);
    if (text) params.set("q", text);
    fetch(`${URL}?${params}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((body: unknown) => {
        if (!isPage<WalkInStudent>(body)) throw new Error("not a page");
        setData(body);
      })
      .catch(() => setLoadFailed(true));
  }, []);

  useEffect(() => {
    load(offset, source, q);
  }, [load, offset, source, q]);

  const reload = () => load(offset, source, q);

  function filter(nextSource: string, nextQ: string) {
    setOffset(0);
    setSource(nextSource);
    setQ(nextQ);
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    filter(source, typed.trim());
  }

  return (
    <div className="action-card">
      <h3>My students</h3>
      <p className="muted" style={{ fontSize: 13 }}>Your walk-in students, converted leads and the students of the applications assigned to you.</p>
      <form role="search" aria-label="Filter my students" onSubmit={search} style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 8, marginBottom: 12 }}>
        <div className="field" style={{ flex: "1 1 200px", marginBottom: 0 }}><label htmlFor="my-students-q">Search</label><input id="my-students-q" type="search" value={typed} onChange={(e) => setTyped(e.target.value)} maxLength={100} placeholder="Name, email or phone" autoComplete="off" /></div>
        <div className="field" style={{ flex: "0 1 180px", marginBottom: 0 }}>
          <label htmlFor="my-students-source">Source</label>
          <select id="my-students-source" value={source} onChange={(e) => filter(e.target.value, q)}>
            <option value="">All sources</option>
            {Object.entries(SOURCE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <button className="btn secondary small">Search</button>
        {(filtered || typed !== "") && <button type="button" className="btn secondary small" onClick={() => { setTyped(""); filter("", ""); }}>Clear</button>}
      </form>
      {/* csc-003: row results (resend, edit) are announced here; always mounted, styled only while it has something to say. */}
      <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8, overflowWrap: "anywhere" } : undefined}>{notice}</div>
      {loadFailed ? (
        <>
          <p className="form-error" role="alert">Unable to load your students.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </>
      ) : data === null ? (
        <p className="muted" aria-busy="true">Loading your students…</p>
      ) : data.items.length === 0 ? (
        <p className="muted">{filtered ? "No students match these filters." : "No students yet. Add a walk-in student below."}</p>
      ) : (
        <ul style={{ paddingLeft: 0, listStyle: "none" }}>
          {data.items.map((s) => (
            <CounselorWalkInStudentRow
              key={s.id}
              student={s}
              onChanged={(message) => {
                setNotice(message);
                reload();
              }}
            />
          ))}
        </ul>
      )}
      {data !== null && data.total > PAGE_SIZE && (
        <nav aria-label="Student pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginBottom: 12 }}>
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

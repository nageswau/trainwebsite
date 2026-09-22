"use client";

import { type FormEvent, useEffect, useState } from "react";

import SchoolSkillAlert from "@/components/SchoolSkillAlert";
import { SkillStatus, useSkillAction, type SkillAction } from "@/components/useSkillAction";
import { formatDate } from "@/lib/formatDate";
import { canMark, type SkillBatchDetail, type SkillSession } from "@/lib/skills";

// ENH-011 spec §7: sessions (one per day, D10) and a labelled checkbox roster per session. Only students who can still be marked are
// listed (not certified, withdrawn or transferred out). Unsaved marks are flagged and guarded against leaving the page; a failed save
// keeps them. On a closed batch the section is read-only.
const BASE = "/api/v1/school/career-counselor";
const LEAVE_WITH_UNSAVED = "You have unsaved attendance. Leave this page without saving it?";
const sessionLabel = (s: SkillSession) => `${formatDate(s.session_date)}${s.topic ? ` — ${s.topic}` : ""}`;

export default function SchoolSkillAttendance({ batch }: { batch: SkillBatchDetail }) {
  const action = useSkillAction();
  const [date, setDate] = useState("");
  const [topic, setTopic] = useState("");
  const [selectedId, setSelectedId] = useState(batch.sessions.at(-1)?.id ?? "");
  const session = batch.sessions.find((s) => s.id === selectedId) ?? batch.sessions.at(-1);
  const open = batch.status === "open";

  async function addSession(e: FormEvent) {
    e.preventDefault();
    const created = await action.run<SkillSession>(`${BASE}/skill-batches/${batch.id}/sessions`, "POST", { session_date: date, topic: topic.trim() || null }, (s) => `Session on ${formatDate(s.session_date)} added.`);
    if (created) {
      setDate("");
      setTopic("");
      setSelectedId(created.id);
    }
  }

  return (
    <div className="card" aria-busy={action.busy}>
      <h2>Sessions and attendance</h2>
      <SkillStatus message={action.message} />
      <SchoolSkillAlert alert={action.alert} />
      {open && (
        <form className="form" onSubmit={addSession}>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="skill-session-date">Session date</label>
              <input id="skill-session-date" type="date" className="search" required min={batch.start_date} max={batch.end_date ?? undefined} value={date} disabled={action.busy} onChange={(e) => setDate(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="skill-session-topic">Session topic (optional)</label>
              <input id="skill-session-topic" className="search" maxLength={160} value={topic} disabled={action.busy} onChange={(e) => setTopic(e.target.value)} />
            </div>
          </div>
          <button type="submit" className="btn secondary small" disabled={action.busy || !date}>Add session</button>
        </form>
      )}
      {!session ? (
        <p className="muted">No sessions yet. Add one to start taking attendance.</p>
      ) : (
        <>
          <div className="field">
            <label htmlFor="skill-session-pick">Session</label>
            <select id="skill-session-pick" className="select" value={session.id} onChange={(e) => setSelectedId(e.target.value)}>
              {batch.sessions.map((s) => <option key={s.id} value={s.id}>{sessionLabel(s)}</option>)}
            </select>
          </div>
          {open ? (
            <AttendanceRoster key={`${session.id}:${JSON.stringify(session.attendance)}`} batch={batch} session={session} action={action} />
          ) : (
            <ul>
              {batch.enrollments.map((e) => {
                const mark = session.attendance.find((a) => a.enrollment_id === e.id);
                return <li key={e.id}>{`${e.student_name}: ${mark ? (mark.present ? "Present" : "Absent") : "Not marked"}`}</li>;
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function AttendanceRoster({ batch, session, action }: { batch: SkillBatchDetail; session: SkillSession; action: SkillAction }) {
  const markable = batch.enrollments.filter(canMark);
  const saved = Object.fromEntries(session.attendance.map((a) => [a.enrollment_id, a.present]));
  const [present, setPresent] = useState<Record<string, boolean>>(() => Object.fromEntries(markable.map((e) => [e.id, saved[e.id] ?? false])));
  const dirty = markable.some((e) => present[e.id] !== (saved[e.id] ?? false));

  useEffect(() => {
    if (!dirty) return;
    // A reload or closing the tab: the browser's own prompt.
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    // An in-app link (sidebar, "All skills batches") is a client navigation that never fires `beforeunload` (browser QA-02). This
    // capture-phase listener runs before Next's <Link> handler; "stay" stops both it and the browser's own navigation.
    const guardLinks = (event: MouseEvent) => {
      const link = (event.target as Element | null)?.closest?.("a[href]");
      if (!link || link.getAttribute("target") === "_blank") return;
      if (!window.confirm(LEAVE_WITH_UNSAVED)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", guardLinks, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", guardLinks, true);
    };
  }, [dirty]);

  function save(e: FormEvent) {
    e.preventDefault();
    const records = markable.map((m) => ({ enrollment_id: m.id, present: present[m.id] }));
    void action.run(`${BASE}/skill-sessions/${session.id}/attendance`, "PUT", { records }, () => `Attendance saved for ${formatDate(session.session_date)}.`);
  }

  if (markable.length === 0) return <p className="muted">No student in this batch can be marked: they are certified, withdrawn or have moved school.</p>;
  return (
    <form className="form" onSubmit={save}>
      <fieldset style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        <legend>Attendance for {sessionLabel(session)}</legend>
        <div style={{ display: "grid", gap: 4 }}>
          {markable.map((m) => (
            <label key={m.id} style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 44 }}>
              <input type="checkbox" checked={present[m.id]} disabled={action.busy} onChange={(e) => setPresent((p) => ({ ...p, [m.id]: e.target.checked }))} />
              {m.student_name}
            </label>
          ))}
        </div>
      </fieldset>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
        <button type="button" className="btn secondary small" disabled={action.busy} onClick={() => setPresent(Object.fromEntries(markable.map((m) => [m.id, true])))}>Mark all present</button>
        <button type="submit" className="btn small" disabled={action.busy}>{action.busy ? "Saving…" : "Save attendance"}</button>
        {dirty && <span className="muted">Unsaved changes</span>}
      </div>
    </form>
  );
}

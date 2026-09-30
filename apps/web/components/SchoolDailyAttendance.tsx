"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState, useTransition } from "react";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { sendJson } from "@/lib/apiErrors";
import { ATTENDANCE_LABEL, ATTENDANCE_STATUSES, type AttendanceStatus } from "@/lib/attendance";
import { formatCalendarDate } from "@/lib/formatDate";

// ENH-030 spec §6: the teacher marks their assigned class for one day with one Save (DEC-SCOPE-038 D1/D2). Four labelled radios per
// student (D4); an unmarked student starts with nothing chosen (C2) and "Mark all present" fills only those. The date picker's max is
// the server's school-calendar "today", never the browser clock. Unsaved marks are flagged and guarded against leaving the page.
export type RosterStudent = { id: string; full_name: string; grade_or_class: string | null; status: AttendanceStatus | null };
export type DailyRoster = { session_date: string; today: string; students: RosterStudent[] };

type Marks = Record<string, AttendanceStatus | null>;
const PAGE = "/school/teacher/attendance";
const LEAVE_WITH_UNSAVED = "You have unsaved attendance. Leave without saving it?";
const savedMarks = (roster: DailyRoster): Marks => Object.fromEntries(roster.students.map((s) => [s.id, s.status]));
const plural = (n: number) => `${n} student${n === 1 ? "" : "s"}`;

export default function SchoolDailyAttendance({ roster }: { roster: DailyRoster }) {
  const router = useRouter();
  const saved = savedMarks(roster);
  const [marks, setMarks] = useState<Marks>(() => savedMarks(roster));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const [loadingDate, startDateChange] = useTransition(); // spec §11 F1: feedback while the next day's roster loads
  const locked = busy || loadingDate;
  const dirty = roster.students.some((s) => marks[s.id] !== saved[s.id]);
  const marked = roster.students.filter((s) => marks[s.id]).length;

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    // Same guard as SchoolSkillAttendance: an in-app link is a client navigation that never fires `beforeunload`.
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

  function changeDate(value: string) {
    if (!value || value === roster.session_date) return;
    if (dirty && !window.confirm(LEAVE_WITH_UNSAVED)) return;
    startDateChange(() => router.push(`${PAGE}?date=${value}`));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    const records = roster.students.flatMap((s) => (marks[s.id] ? [{ student_id: s.id, status: marks[s.id] }] : []));
    if (records.length === 0) {
      setMessage({ text: "Choose a status for at least one student.", failed: true });
      return;
    }
    setBusy(true);
    setMessage(null);
    const outcome = await sendJson("/api/v1/school/attendance", "PUT", { session_date: roster.session_date, records });
    setBusy(false);
    if (!outcome.ok) {
      setMessage({ text: outcome.message, failed: true });
      return;
    }
    const left = roster.students.length - records.length;
    setMessage({ text: `Attendance saved for ${plural(records.length)} on ${formatCalendarDate(roster.session_date)}.${left ? ` ${left} left unmarked.` : ""}`, failed: false });
    router.refresh();
  }

  if (roster.students.length === 0) {
    return <p className="muted" role="status">No students assigned to you yet. Your School Coordinator assigns students to teachers.</p>;
  }
  return (
    <form className="form" onSubmit={save} aria-busy={locked}>
      <div className="field" style={{ maxWidth: 220 }}>
        <label htmlFor="attendance-date">Date</label>
        <input id="attendance-date" type="date" value={roster.session_date} max={roster.today} disabled={locked} onChange={(e) => changeDate(e.target.value)} />
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
        <p className="muted" style={{ margin: 0 }}>{loadingDate ? "Loading the selected date…" : `${marked} of ${plural(roster.students.length)} marked`}</p>
        <button type="button" className="btn secondary small" disabled={locked} onClick={() => setMarks((m) => Object.fromEntries(roster.students.map((s) => [s.id, m[s.id] ?? "present"])))}>
          Mark all present
        </button>
      </div>
      <div style={{ display: "grid", gap: 12 }}>
        {roster.students.map((s) => (
          <fieldset key={s.id} style={{ border: 0, borderTop: "1px solid var(--line)", padding: "8px 0 0", margin: 0, minWidth: 0 }}>
            <legend style={{ padding: 0 }}>
              <strong>{s.full_name}</strong>
              {s.grade_or_class ? <span className="muted"> · {s.grade_or_class}</span> : null}
              {saved[s.id] === null ? <> <span className="badge">Not marked</span></> : null}
            </legend>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0 18px" }}>
              {ATTENDANCE_STATUSES.map((status) => (
                <label key={status} style={{ display: "inline-flex", alignItems: "center", gap: 8, minHeight: 44 }}>
                  <input type="radio" name={`attendance-${s.id}`} value={status} checked={marks[s.id] === status} disabled={locked} onChange={() => setMarks((m) => ({ ...m, [s.id]: status }))} />
                  {ATTENDANCE_LABEL[status]}
                </label>
              ))}
            </div>
          </fieldset>
        ))}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
        <button type="submit" className="btn small" disabled={locked}>{busy ? "Saving…" : "Save attendance"}</button>
        {dirty && <span className="muted">Unsaved changes</span>}
      </div>
      {message && <FormMessage message={message} />}
    </form>
  );
}

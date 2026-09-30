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
const NOT_ASSIGNED = "One or more students are not assigned to you"; // the API's scope refusal (school_attendance.py)
const CLASS_CHANGED = "Your class list changed since this page was opened, so nothing was saved. The list has been updated — check the marks and save again.";
const savedMarks = (roster: DailyRoster): Marks => Object.fromEntries(roster.students.map((s) => [s.id, s.status]));
const plural = (n: number) => `${n} student${n === 1 ? "" : "s"}`;

export default function SchoolDailyAttendance({ roster: rosterProp }: { roster: DailyRoster }) {
  const router = useRouter();
  // QA30-04: the roster on screen. A successful save replaces it with the server's answer at once (the PUT returns the day's
  // roster), so "Unsaved changes" and "Not marked" never lag behind router.refresh(); a new prop (a refresh, another tab) wins again.
  const [roster, setRoster] = useState(rosterProp);
  const [lastProp, setLastProp] = useState(rosterProp);
  if (rosterProp !== lastProp) {
    setLastProp(rosterProp);
    setRoster(rosterProp);
  }
  const saved = savedMarks(roster);
  const [marks, setMarks] = useState<Marks>(() => savedMarks(rosterProp));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const [pickedDate, setPickedDate] = useState(rosterProp.session_date);
  const [loadingDate, startDateChange] = useTransition(); // spec §11 F1: feedback while the next day's roster loads
  const locked = busy || loadingDate;
  // `?? null`: a student who appeared after a refresh has no entry in `marks` yet, and that is not a change (QA30-04).
  const dirty = roster.students.some((s) => (marks[s.id] ?? null) !== (saved[s.id] ?? null));
  const marked = roster.students.filter((s) => marks[s.id]).length;
  // QA30-01: the field may hold a date the teacher has not opened yet; the list (and Save) still belong to `roster.session_date`.
  const dateNote = pickedDate === roster.session_date ? null : !pickedDate ? "Choose a date and press Show."
    : pickedDate > roster.today ? `${formatCalendarDate(pickedDate)} is in the future; attendance cannot be marked for it.`
    : `Showing ${formatCalendarDate(roster.session_date)}. Press Show to open ${formatCalendarDate(pickedDate)}.`;

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
    // QA30-02: browser Back/Forward is a history change the two guards above never see. This capture listener runs before the
    // router's own popstate handler. Staying stops that handler and tells the router to show this page's own URL again in place of
    // the entry the browser moved to -- whatever the direction or distance of the move (review I-1: no history.go guess, no
    // swallowed follow-up event). The key does not change, so the form keeps its marks.
    const guardHistory = (event: PopStateEvent) => {
      if (window.confirm(LEAVE_WITH_UNSAVED)) return;
      event.stopImmediatePropagation();
      router.replace(`${PAGE}?date=${roster.session_date}`, { scroll: false });
    };
    window.addEventListener("beforeunload", warn);
    window.addEventListener("popstate", guardHistory, true);
    document.addEventListener("click", guardLinks, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      window.removeEventListener("popstate", guardHistory, true);
      document.removeEventListener("click", guardLinks, true);
    };
  }, [dirty, router, roster.session_date]);

  // Final review I2: a date input fires change per typed segment, so the field keeps its own value and the page navigates only when
  // the teacher asks (Show, or Enter in the field) -- keyboard and screen-reader entry can then finish typing a whole date.
  function showDate(event: FormEvent) {
    event.preventDefault();
    if (!pickedDate || pickedDate === roster.session_date) return;
    if (dirty && !window.confirm(LEAVE_WITH_UNSAVED)) return;
    startDateChange(() => router.push(`${PAGE}?date=${pickedDate}`));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (dateNote) {
      // QA30-01: never write to a date other than the one the field shows.
      setMessage({ text: `${dateNote} To save ${formatCalendarDate(roster.session_date)}, set the date back to it.`, failed: true });
      return;
    }
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
      // Review I-2: the class list changed under the teacher (a reassignment or transfer -> 403 scope; a transfer in progress -> 409).
      // Refresh the list in place -- the key is unchanged and `marks` is keyed by student, so every remaining mark is kept.
      const classChanged = outcome.status === 403 && outcome.message === NOT_ASSIGNED;
      setMessage({ text: classChanged ? CLASS_CHANGED : outcome.message, failed: true });
      if (classChanged || outcome.status === 409) router.refresh();
      return;
    }
    const left = roster.students.length - records.length;
    setMessage({ text: `Attendance saved for ${plural(records.length)} on ${formatCalendarDate(roster.session_date)}.${left ? ` ${left} left unmarked.` : ""}`, failed: false });
    if (Array.isArray(outcome.data.students)) setRoster(outcome.data as unknown as DailyRoster); // QA30-04
    router.refresh();
  }

  // Review I-3: a past day lists only students already enrolled at this school that day, so an empty past day is not "no class".
  const emptyText = roster.session_date === roster.today
    ? "No students assigned to you yet. Your School Coordinator assigns students to teachers."
    : `None of your current students were enrolled at your school on ${formatCalendarDate(roster.session_date)}.`;
  return (
    <>
      <form className="form" onSubmit={showDate} style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
          <div className="field" style={{ maxWidth: 220, margin: 0 }}>
            <label htmlFor="attendance-date">Date</label>
            <input id="attendance-date" type="date" value={pickedDate} max={roster.today} disabled={locked} onChange={(e) => setPickedDate(e.target.value)} />
          </div>
          <button type="submit" className="btn secondary small" disabled={locked}>Show</button>
        </div>
        {dateNote && <p className="form-warning" aria-live="polite" style={{ margin: "8px 0 0" }}>{dateNote}</p>}
      </form>
      {roster.students.length === 0 ? (
        <p className="muted" role="status">{emptyText}</p>
      ) : (
        <form className="form" onSubmit={save} aria-busy={locked}>
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
      )}
    </>
  );
}

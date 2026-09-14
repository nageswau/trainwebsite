"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { University } from "@/lib/types";

type LinkedStudent = { link_id: string; student_id: string; student: string; email: string; status: string };
type Course = { id: string; title: string; level: string };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to submit the application.";
}

// RAID.md I-32 (Tier 0 of the reference-dropdown audit) -- "Linked student reference",
// "University reference" and "Course reference" used to be bare typed UUID fields; an
// agent had no way to see this without a second browser tab open on the API. The backend
// (`create_overseas_application`, workflows.py) already requires the student to be one of
// this agent's own *active* links (`AgentStudent.status == "active"`, else 403) -- exactly
// the same bounded, already-fetchable list `GET /overseas/agent/students` returns, so it's
// a real dropdown, not a typeahead over an unbounded catalogue. University/Course reuse the
// exact cascading picker `OverseasApplyPanel` (OVS-002) already built for the student's own
// self-service apply flow, rather than inventing a second implementation of the same thing.
export default function AgentApplicationCreatePanel() {
  const router = useRouter();
  const [students, setStudents] = useState<LinkedStudent[] | null>(null);
  const [universities, setUniversities] = useState<University[] | null>(null);
  const [studentId, setStudentId] = useState("");
  const [universityId, setUniversityId] = useState("");
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [courseId, setCourseId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/workflows/overseas/agent/students")
      .then((res) => (res.ok ? res.json() : []))
      .then((data: LinkedStudent[]) => !cancelled && setStudents(data.filter((s) => s.status === "active")))
      .catch(() => !cancelled && setStudents([]));
    fetch("/api/v1/public/universities")
      .then((res) => (res.ok ? res.json() : []))
      .then((data: University[]) => !cancelled && setUniversities(data))
      .catch(() => !cancelled && setUniversities([]));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setCourseId("");
    if (!universityId) {
      setCourses(null);
      return;
    }
    const university = universities?.find((u) => u.id === universityId);
    if (!university) return;
    let cancelled = false;
    fetch(`/api/v1/public/universities/${university.slug}`)
      .then((res) => (res.ok ? res.json() : { courses: [] }))
      .then((data) => !cancelled && setCourses(data.courses || []))
      .catch(() => !cancelled && setCourses([]));
    return () => {
      cancelled = true;
    };
  }, [universityId, universities]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/v1/workflows/overseas/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        student_id: studentId,
        university_id: universityId,
        course_id: courseId || null,
        intake: String(form.get("intake") || "Next intake"),
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: "Application created.", failed: false });
    setStudentId("");
    setUniversityId("");
    setCourses(null);
    router.refresh();
  }

  if (students === null || universities === null) {
    return (
      <div className="action-card">
        <h3>Create application</h3>
        <p className="muted">Loading your linked students…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Create application</h3>
      {!students.length && <p className="muted">No actively linked students yet -- link a student first.</p>}
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="agent-app-student">Linked student</label>
          <select id="agent-app-student" value={studentId} onChange={(event) => setStudentId(event.target.value)} required disabled={!students.length}>
            <option value="">Select student</option>
            {students.map((s) => (
              <option key={s.student_id} value={s.student_id}>
                {s.student} -- {s.email}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="agent-app-university">University</label>
          <select id="agent-app-university" value={universityId} onChange={(event) => setUniversityId(event.target.value)} required>
            <option value="">Select university</option>
            {universities.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name} -- {u.city}
              </option>
            ))}
          </select>
        </div>
        {universityId && (
          <div className="field">
            <label htmlFor="agent-app-course">Course (optional)</label>
            <select id="agent-app-course" value={courseId} onChange={(event) => setCourseId(event.target.value)} disabled={courses === null}>
              <option value="">Undecided / any course</option>
              {(courses || []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title} ({c.level})
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="field">
          <label htmlFor="agent-app-intake">Intake</label>
          <input id="agent-app-intake" name="intake" defaultValue="Next intake" required />
        </div>
        <button className="btn" disabled={busy || !students.length || !studentId || !universityId}>
          {busy ? "Creating…" : "Create application"}
        </button>
      </form>
      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
    </div>
  );
}

"use client";

import { FormEvent, useEffect, useState } from "react";

type UniversityOption = { id: string; name: string; city: string };
type BridgedApplication = { id: string; student_name: string; student_code: string; university_name: string; status: string; created_at: string };
type ResolvedStudent = { id: string; full_name: string; student_code: string; school_name: string | null };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to complete this action.";
}

// DEC-SCOPE-018 (2026-09-15): Overseas Admin/Counselor links a School-affiliated student
// to a real Overseas application -- never school_coordinator, per direct decision. Looks
// the student up by their business-facing Student ID (DEC-DATA-003's own 8-character
// code) rather than a raw internal id picker, since Overseas Admin/Counselor need to find
// a student across every partner school, not just one they're already scoped to.
export default function AdminSchoolApplicationsPanel() {
  const [universities, setUniversities] = useState<UniversityOption[]>([]);
  const [applications, setApplications] = useState<BridgedApplication[] | null>(null);
  const [studentCode, setStudentCode] = useState("");
  const [resolved, setResolved] = useState<ResolvedStudent | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  function loadApplications() {
    fetch("/api/v1/overseas-admin/school-applications")
      .then((res) => (res.ok ? res.json() : []))
      .then(setApplications)
      .catch(() => setApplications([]));
  }

  useEffect(() => {
    fetch("/api/v1/public/universities")
      .then((res) => (res.ok ? res.json() : []))
      .then((data: UniversityOption[]) => setUniversities(data))
      .catch(() => setUniversities([]));
    loadApplications();
  }, []);

  async function lookupStudent() {
    setMessage(null);
    setResolved(null);
    const code = studentCode.trim().toUpperCase();
    if (!code) return;
    const response = await fetch(`/api/v1/overseas-admin/school-students/lookup?code=${encodeURIComponent(code)}`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setResolved(data);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resolved) {
      setMessage({ text: "Look up a student by their Student ID first.", failed: true });
      return;
    }
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setMessage(null);
    const response = await fetch(`/api/v1/overseas-admin/school-students/${resolved.id}/applications`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ university_id: form.get("university_id"), intake: form.get("intake") }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: `Application started for ${resolved.full_name}.`, failed: false });
    setStudentCode("");
    setResolved(null);
    loadApplications();
  }

  return (
    <div className="action-card">
      <h3>Start an Overseas application for a School student</h3>
      <div className="field">
        <label htmlFor="bridge-student-code">Student ID</label>
        <div style={{ display: "flex", gap: 8 }}>
          <input id="bridge-student-code" value={studentCode} onChange={(event) => setStudentCode(event.target.value)} placeholder="e.g. A3F9C21B" />
          <button type="button" className="btn secondary" onClick={lookupStudent}>Look up</button>
        </div>
        {resolved && (
          <p className="muted" style={{ fontSize: 13 }}>{resolved.full_name} — {resolved.school_name}</p>
        )}
      </div>
      {resolved && (
        <form className="form" onSubmit={submit}>
          <div className="field">
            <label htmlFor="bridge-university">University</label>
            <select id="bridge-university" name="university_id" required defaultValue="">
              <option value="" disabled>Select university</option>
              {universities.map((u) => (
                <option key={u.id} value={u.id}>{u.name} ({u.city})</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="bridge-intake">Intake</label>
            <input id="bridge-intake" name="intake" required placeholder="e.g. Fall 2027" />
          </div>
          <button className="btn" disabled={busy}>{busy ? "Starting…" : "Start application"}</button>
        </form>
      )}
      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
      <div className="table-wrap" style={{ marginTop: 16 }}>
        <h4>Linked applications</h4>
        {!applications || applications.length === 0 ? (
          <p className="muted">No School-linked applications yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Student</th><th>Student ID</th><th>University</th><th>Status</th></tr>
            </thead>
            <tbody>
              {applications.map((a) => (
                <tr key={a.id}><td>{a.student_name}</td><td><code>{a.student_code}</code></td><td>{a.university_name}</td><td>{a.status}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

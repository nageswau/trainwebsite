"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

type Student = { id: string; full_name: string; school_name: string };
type Result = {
  id: string; school_student_id: string; academic_year: string; term: string; subject: string;
  max_marks: number; marks_obtained: number; percentage: number | null; grade: string | null;
  status: string; uploaded_by_user_id: string; verified_by_user_id: string | null; published_by_user_id: string | null;
};

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Something went wrong.";
}

// SCH-006: Academic Team uploads a result (Draft) -> a DIFFERENT Academic Team member
// verifies -> publishes (Verified -> Published). DEC-ROLE-007's same-actor restriction
// means the uploader never sees a working Verify/Publish action on their own upload here.
export default function SchoolAcademicResultsPanel({ results, students, currentUserId }: { results: Result[]; students: Student[]; currentUserId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  async function createResult(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    const response = await fetch("/api/v1/school/academic-team/results", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        school_student_id: form.get("school_student_id"),
        academic_year: form.get("academic_year"),
        term: form.get("term"),
        subject: form.get("subject"),
        max_marks: Number(form.get("max_marks")),
        marks_obtained: Number(form.get("marks_obtained")),
        grade: form.get("grade") || undefined,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: `${data.subject} result saved as Draft.`, failed: false });
    formElement.reset();
    router.refresh();
  }

  async function advance(resultId: string, action: "verify" | "publish") {
    setBusy(true);
    setMessage(null);
    const response = await fetch(`/api/v1/school/academic-team/results/${resultId}/${action}`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: `Result ${action === "verify" ? "verified" : "published"}.`, failed: false });
    router.refresh();
  }

  function studentName(id: string) {
    return students.find((s) => s.id === id)?.full_name || "Unknown student";
  }

  return (
    <div className="portal-content">
      <div className="card">
        <h2>Results</h2>
        {results.length === 0 ? (
          <p className="muted">No results uploaded yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Student</th><th>Subject</th><th>Marks</th><th>Status</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {results.map((r) => {
                  const isUploader = r.uploaded_by_user_id === currentUserId;
                  return (
                    <tr key={r.id}>
                      <td>{studentName(r.school_student_id)}</td>
                      <td>{r.subject} ({r.academic_year}, {r.term})</td>
                      <td>{r.marks_obtained}/{r.max_marks}{r.percentage !== null ? ` (${r.percentage}%)` : ""}</td>
                      <td>{r.status}</td>
                      <td>
                        {r.status === "draft" && (
                          isUploader ? (
                            <span className="muted" style={{ fontSize: 13 }}>Ask another Academic Team member to verify</span>
                          ) : (
                            <button className="btn ghost small" disabled={busy} onClick={() => advance(r.id, "verify")}>Verify</button>
                          )
                        )}
                        {r.status === "verified" && (
                          isUploader ? (
                            <span className="muted" style={{ fontSize: 13 }}>Ask another Academic Team member to publish</span>
                          ) : (
                            <button className="btn ghost small" disabled={busy} onClick={() => advance(r.id, "publish")}>Publish</button>
                          )
                        )}
                        {r.status === "published" && <span className="muted" style={{ fontSize: 13 }}>-</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="action-card">
        <h3>Upload a result</h3>
        {students.length === 0 ? (
          <p className="muted">No students in your portfolio yet. Contact your Overseas Admin.</p>
        ) : (
          <form className="form" onSubmit={createResult}>
            <div className="field">
              <label htmlFor="result-student">Student</label>
              <select id="result-student" name="school_student_id" required defaultValue="">
                <option value="" disabled>Select student</option>
                {students.map((s) => (
                  <option key={s.id} value={s.id}>{s.full_name} — {s.school_name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="result-year">Academic year</label>
              <input id="result-year" name="academic_year" placeholder="2026" required />
            </div>
            <div className="field">
              <label htmlFor="result-term">Term</label>
              <input id="result-term" name="term" placeholder="Term 1" required />
            </div>
            <div className="field">
              <label htmlFor="result-subject">Subject</label>
              <input id="result-subject" name="subject" required />
            </div>
            <div className="field">
              <label htmlFor="result-max">Maximum marks</label>
              <input id="result-max" name="max_marks" type="number" step="0.01" required />
            </div>
            <div className="field">
              <label htmlFor="result-obtained">Marks obtained</label>
              <input id="result-obtained" name="marks_obtained" type="number" step="0.01" required />
            </div>
            <div className="field">
              <label htmlFor="result-grade">Grade</label>
              <input id="result-grade" name="grade" placeholder="Optional" />
            </div>
            <button className="btn" disabled={busy}>{busy ? "Saving…" : "Save as Draft"}</button>
          </form>
        )}
      </div>

      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite">
          {message.text}
        </div>
      )}
    </div>
  );
}

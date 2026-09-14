"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

type Student = { id: string; full_name: string; school_name: string };
type Record_ = { id: string; school_student_id: string; assessment_type: string; report_url: string | null; status: string; created_at: string };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Something went wrong.";
}

// SCH-005: Psychometric Team assigns an assessment, then uploads a report against it --
// visible to readers immediately, no Draft/Published gate for this content.
export default function SchoolPsychometricRecordsPanel({ records, students }: { records: Record_[]; students: Student[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [uploadingId, setUploadingId] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    const response = await fetch("/api/v1/school/psychometric-team/records", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ school_student_id: form.get("school_student_id"), assessment_type: form.get("assessment_type") }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: "Assessment assigned.", failed: false });
    formElement.reset();
    router.refresh();
  }

  async function attachReport(event: FormEvent<HTMLFormElement>, recordId: string) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch(`/api/v1/school/psychometric-team/records/${recordId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report_url: form.get("report_url") }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: "Report attached.", failed: false });
    setUploadingId(null);
    router.refresh();
  }

  function studentName(id: string) {
    return students.find((s) => s.id === id)?.full_name || "Unknown student";
  }

  return (
    <div className="portal-content">
      <div className="card">
        <h2>Assessments</h2>
        {records.length === 0 ? (
          <p className="muted">No assessments assigned yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Student</th><th>Assessment</th><th>Status</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id}>
                  <td>{studentName(r.school_student_id)}</td>
                  <td>{r.assessment_type}</td>
                  <td>{r.status}</td>
                  <td>
                    {r.status === "assigned" ? (
                      <button className="btn ghost small" onClick={() => setUploadingId(r.id)}>Attach report</button>
                    ) : (
                      <span className="muted" style={{ fontSize: 13 }}>Report attached</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {uploadingId && (
        <div className="action-card">
          <h3>Attach report</h3>
          <form className="form" onSubmit={(e) => attachReport(e, uploadingId)}>
            <div className="field">
              <label htmlFor="report-url">Report URL</label>
              <input id="report-url" name="report_url" required placeholder="/local-files/uploads/report.pdf" />
            </div>
            <div className="field" style={{ flexDirection: "row", gap: 12 }}>
              <button className="btn" disabled={busy}>{busy ? "Saving…" : "Attach"}</button>
              <button type="button" className="btn secondary" onClick={() => setUploadingId(null)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      <div className="action-card">
        <h3>Assign an assessment</h3>
        {students.length === 0 ? (
          <p className="muted">No students in your portfolio yet. Contact your Overseas Admin.</p>
        ) : (
          <form className="form" onSubmit={submit}>
            <div className="field">
              <label htmlFor="psych-student">Student</label>
              <select id="psych-student" name="school_student_id" required defaultValue="">
                <option value="" disabled>Select student</option>
                {students.map((s) => (
                  <option key={s.id} value={s.id}>{s.full_name} — {s.school_name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="psych-type">Assessment type</label>
              <input id="psych-type" name="assessment_type" required placeholder="e.g. Aptitude Test" />
            </div>
            <button className="btn" disabled={busy}>{busy ? "Saving…" : "Assign assessment"}</button>
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

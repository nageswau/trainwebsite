"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { sendJson } from "@/lib/apiErrors";

type Student = { id: string; full_name: string; school_name: string };
type Record_ = { id: string; school_student_id: string; record_type: string; notes: string; created_at: string };

const TYPE_LABEL: Record<string, string> = { guidance_session: "Guidance session", counselling_note: "Counselling note", recommendation: "Recommendation" };

// SCH-004: Career Counselor adds a guidance session, counselling note, or recommendation --
// visible to readers immediately, no Draft/Published gate for this content unlike results.
export default function SchoolCareerRecordsPanel({ records, students }: { records: Record_[]; students: Student[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    const result = await sendJson("/api/v1/school/career-counselor/records", "POST", { school_student_id: form.get("school_student_id"), record_type: form.get("record_type"), notes: form.get("notes") });
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true });
      return;
    }
    setMessage({ text: "Record saved.", failed: false });
    formElement.reset();
    router.refresh();
  }

  function studentName(id: string) {
    return students.find((s) => s.id === id)?.full_name || "Unknown student";
  }

  return (
    <div className="portal-content">
      <div className="card">
        <h2>Records</h2>
        {records.length === 0 ? (
          <p className="muted">No career guidance or counselling recorded yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Student</th><th>Type</th><th>Notes</th></tr>
              </thead>
              <tbody>
                {records.map((r) => (
                  <tr key={r.id}><td>{studentName(r.school_student_id)}</td><td>{TYPE_LABEL[r.record_type] || r.record_type}</td><td>{r.notes}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="action-card">
        <h3>Add a record</h3>
        {students.length === 0 ? (
          <p className="muted">No students in your portfolio yet. Contact your Overseas Admin.</p>
        ) : (
          <form className="form" onSubmit={submit}>
            <div className="field">
              <label htmlFor="career-student">Student</label>
              <select id="career-student" name="school_student_id" required defaultValue="">
                <option value="" disabled>Select student</option>
                {students.map((s) => (
                  <option key={s.id} value={s.id}>{s.full_name} — {s.school_name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="career-type">Type</label>
              <select id="career-type" name="record_type" required defaultValue="">
                <option value="" disabled>Select type</option>
                <option value="guidance_session">Guidance session</option>
                <option value="counselling_note">Counselling note</option>
                <option value="recommendation">Recommendation</option>
              </select>
            </div>
            <div className="field full">
              <label htmlFor="career-notes">Notes</label>
              <textarea id="career-notes" name="notes" required />
            </div>
            <button className="btn" disabled={busy}>{busy ? "Saving…" : "Save record"}</button>
          </form>
        )}
        {message && <FormMessage message={message} />}
      </div>
    </div>
  );
}

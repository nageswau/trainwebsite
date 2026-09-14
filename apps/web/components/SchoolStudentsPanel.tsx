"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

type Student = {
  id: string;
  full_name: string;
  date_of_birth: string | null;
  grade_or_class: string | null;
  assigned_teacher_user_id: string | null;
};

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Something went wrong.";
}

// SCH-001: the Coordinator's working roster -- add one student by hand, edit an existing
// one, link a Parent account to a student. Bulk upload is a separate Feature ID (SCH-002),
// not built here.
export default function SchoolStudentsPanel({ students }: { students: Student[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [linkingId, setLinkingId] = useState<string | null>(null);

  async function createStudent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    const response = await fetch("/api/v1/school/students", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: form.get("full_name"),
        grade_or_class: form.get("grade_or_class") || undefined,
        date_of_birth: form.get("date_of_birth") || undefined,
        assigned_teacher_email: form.get("assigned_teacher_email") || undefined,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: `${data.full_name} added to the roster.`, failed: false });
    formElement.reset();
    router.refresh();
  }

  async function saveEdit(event: FormEvent<HTMLFormElement>, studentId: string) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch(`/api/v1/school/students/${studentId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: form.get("full_name"),
        grade_or_class: form.get("grade_or_class") || null,
        assigned_teacher_email: form.get("assigned_teacher_email") || null,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: "Student updated.", failed: false });
    setEditingId(null);
    router.refresh();
  }

  async function linkParent(event: FormEvent<HTMLFormElement>, studentId: string) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch(`/api/v1/school/students/${studentId}/parents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ parent_email: form.get("parent_email") }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: "Parent linked to this student.", failed: false });
    setLinkingId(null);
    router.refresh();
  }

  const editing = students.find((s) => s.id === editingId);
  const linking = students.find((s) => s.id === linkingId);

  return (
    <div className="portal-content">
      <div className="card">
        <h2>Student roster</h2>
        {students.length === 0 ? (
          <p className="muted">No students yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Name</th><th>Grade/Class</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {students.map((s) => (
                <tr key={s.id}>
                  <td>{s.full_name}</td>
                  <td>{s.grade_or_class || "-"}</td>
                  <td style={{ display: "flex", gap: 8 }}>
                    <button className="btn ghost small" onClick={() => { setEditingId(s.id); setLinkingId(null); }}>Edit</button>
                    <button className="btn ghost small" onClick={() => { setLinkingId(s.id); setEditingId(null); }}>Link parent</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editing && (
        <div className="action-card">
          <h3>Edit {editing.full_name}</h3>
          <form className="form" onSubmit={(e) => saveEdit(e, editing.id)}>
            <div className="field">
              <label htmlFor="edit-full-name">Full name</label>
              <input id="edit-full-name" name="full_name" defaultValue={editing.full_name} required />
            </div>
            <div className="field">
              <label htmlFor="edit-grade">Grade/Class</label>
              <input id="edit-grade" name="grade_or_class" defaultValue={editing.grade_or_class || ""} />
            </div>
            <div className="field">
              <label htmlFor="edit-teacher">Assigned Teacher email</label>
              <input id="edit-teacher" name="assigned_teacher_email" type="email" placeholder="Leave blank to unassign" />
            </div>
            <div className="field" style={{ flexDirection: "row", gap: 12 }}>
              <button className="btn" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button>
              <button type="button" className="btn secondary" onClick={() => setEditingId(null)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {linking && (
        <div className="action-card">
          <h3>Link a parent to {linking.full_name}</h3>
          <form className="form" onSubmit={(e) => linkParent(e, linking.id)}>
            <div className="field">
              <label htmlFor="link-parent-email">Parent&apos;s email</label>
              <input id="link-parent-email" name="parent_email" type="email" required />
              <span className="muted" style={{ fontSize: 12 }}>Must already be an accepted Parent account at your own school.</span>
            </div>
            <div className="field" style={{ flexDirection: "row", gap: 12 }}>
              <button className="btn" disabled={busy}>{busy ? "Linking…" : "Link parent"}</button>
              <button type="button" className="btn secondary" onClick={() => setLinkingId(null)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      <div className="action-card">
        <h3>Add one student</h3>
        <form className="form" onSubmit={createStudent}>
          <div className="field">
            <label htmlFor="new-full-name">Full name</label>
            <input id="new-full-name" name="full_name" required />
          </div>
          <div className="field">
            <label htmlFor="new-dob">Date of birth</label>
            <input id="new-dob" name="date_of_birth" type="date" />
          </div>
          <div className="field">
            <label htmlFor="new-grade">Grade/Class</label>
            <input id="new-grade" name="grade_or_class" />
          </div>
          <div className="field">
            <label htmlFor="new-teacher">Assigned Teacher email</label>
            <input id="new-teacher" name="assigned_teacher_email" type="email" placeholder="Optional" />
          </div>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Add student"}</button>
        </form>
        <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>Adding many students at once? <a href="/school/coordinator/students/bulk-upload">Use bulk upload</a> instead.</p>
      </div>

      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite">
          {message.text}
        </div>
      )}
    </div>
  );
}

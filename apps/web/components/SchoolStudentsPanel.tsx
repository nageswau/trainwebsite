"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type Student = {
  id: string;
  full_name: string;
  date_of_birth: string | null;
  grade_or_class: string | null;
  assigned_teacher_user_id: string | null;
  pending_parent_email: string | null;
};

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Something went wrong.";
}

function parentStatusNote(status: string | undefined, email: string) {
  if (status === "linked") return " Parent linked immediately (they already had an account).";
  if (status === "invited") return ` Invite email sent to ${email}.`;
  if (status === "invite_reused") return ` ${email} already has a pending invite from another child -- they'll be linked to both once they accept.`;
  return "";
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
        parent_name: form.get("parent_name") || undefined,
        parent_email: form.get("parent_email") || undefined,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    const parentEmail = String(form.get("parent_email") || "");
    setMessage({ text: `${data.full_name} added to the roster.${parentStatusNote(data.parent_status, parentEmail)}`, failed: false });
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
        parent_name: form.get("parent_name") || undefined,
        parent_email: form.get("parent_email") || undefined,
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    const parentEmail = String(form.get("parent_email") || "");
    setMessage({ text: `Student updated.${parentStatusNote(data.parent_status, parentEmail)}`, failed: false });
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
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Name</th><th>Grade/Class</th><th>Parent</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.id}>
                    <td>{s.full_name}</td>
                    <td>{s.grade_or_class || "-"}</td>
                    <td>{s.pending_parent_email ? <span className="status pending">Invite sent to {s.pending_parent_email}</span> : "-"}</td>
                    <td style={{ display: "flex", gap: 8 }}>
                      <button className="btn ghost small" onClick={() => { setEditingId(s.id); setLinkingId(null); }}>Edit</button>
                      <button className="btn ghost small" onClick={() => { setLinkingId(s.id); setEditingId(null); }}>Link parent</button>
                      <a className="btn ghost small" href={`/school/coordinator/students/${s.id}`}>Timeline</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
            <div className="field">
              <label htmlFor="edit-parent-name">Parent&apos;s name</label>
              <input id="edit-parent-name" name="parent_name" placeholder={editing.pending_parent_email ? "" : "Only used if this parent has no account yet"} />
            </div>
            <div className="field">
              <label htmlFor="edit-parent-email">Parent&apos;s email</label>
              <input id="edit-parent-email" name="parent_email" type="email" defaultValue={editing.pending_parent_email || ""} placeholder="Sends an invite if they don't have an account yet" />
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
          <div className="field">
            <label htmlFor="new-parent-name">Parent&apos;s name</label>
            <input id="new-parent-name" name="parent_name" placeholder="Optional -- only used if they don't have an account yet" />
          </div>
          <div className="field">
            <label htmlFor="new-parent-email">Parent&apos;s email</label>
            <input id="new-parent-email" name="parent_email" type="email" placeholder="Optional -- sends them an invite" />
          </div>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Add student"}</button>
        </form>
        <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>Adding many students at once? <Link href="/school/coordinator/students/bulk-upload">Use bulk upload</Link> instead.</p>
      </div>

      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite">
          {message.text}
        </div>
      )}
    </div>
  );
}

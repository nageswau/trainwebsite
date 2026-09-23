"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import SchoolStudentFields from "@/components/SchoolStudentFields";
import { detailMessage, fieldFromMessage, toMasterPayload, type SchoolStudent } from "@/lib/schoolStudents";

type TeacherOption = { id: string; name: string; active: boolean };
// "roster": a success that closes its card (edit, link parent) is reported on the roster the user returns to.
type FormName = "edit" | "create" | "link" | "roster";
// `field`: the API field a failure is about (QA2-06) -- that input is marked invalid, described by and focused on the error.
type Message = { text: string; failed: boolean; form: FormName; field?: string | null };
const FORM_ID: Partial<Record<FormName, string>> = { edit: "edit-student-form", create: "new-student-form" };
const ERROR_ID = (form: FormName) => `${form}-form-error`;

function failure(data: { detail?: unknown }, form: FormName): Message {
  const raw = typeof data.detail === "string" ? data.detail : "";
  return { text: detailMessage(data.detail), failed: true, form, field: fieldFromMessage(raw) };
}

function parentStatusNote(status: string | undefined, email: string) {
  if (status === "linked") return " Parent linked immediately (they already had an account).";
  if (status === "invited") return ` Invite email sent to ${email}.`;
  if (status === "invite_reused") return ` ${email} already has a pending invite from another child -- they'll be linked to both once they accept.`;
  return "";
}

function FormMessage({ message }: { message: Message }) {
  return message.failed ? (
    <div className="form-error" role="alert" id={ERROR_ID(message.form)}>{message.text}</div>
  ) : (
    <div className="form-message" role="status" aria-live="polite">{message.text}</div>
  );
}

// SCH-001: the Coordinator's working roster -- add one student by hand, edit an existing
// one, link a Parent account to a student. Bulk upload is a separate Feature ID (SCH-002).
// ENH-025: both forms carry the Student Master fields via the shared SchoolStudentFields groups;
// each form shows its own result message next to it, and focus follows the edit card.
export default function SchoolStudentsPanel({ students }: { students: SchoolStudent[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [linkingId, setLinkingId] = useState<string | null>(null);
  const [teachers, setTeachers] = useState<TeacherOption[]>([]);
  const editHeading = useRef<HTMLHeadingElement>(null);
  const lastEditButton = useRef<HTMLButtonElement | null>(null);

  // SCH-001 addendum: a live picker of the school's own Teachers, replacing the
  // hand-typed email field -- the same "raw ID typed by hand" gap already fixed
  // elsewhere in this app (e.g. AdminBatchCreatePanel's trainer picker).
  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/school/team")
      .then((res) => (res.ok ? res.json() : { accounts: [] }))
      .then((data) => {
        if (cancelled) return;
        const options = ((data.accounts || []) as { id: string; name: string; role: string; active: boolean }[])
          .filter((a) => a.role === "school_teacher")
          .map((a) => ({ id: a.id, name: a.name, active: a.active }));
        setTeachers(options);
      })
      .catch(() => !cancelled && setTeachers([]));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!editingId) return;
    editHeading.current?.focus();
    editHeading.current?.scrollIntoView?.({ block: "start" });
  }, [editingId]);

  // QA2-06: move focus to the input a server error is about, so the user lands on what to fix.
  useEffect(() => {
    if (!message?.failed || !message.field) return;
    const name = message.field === "assigned_teacher_email" ? "assigned_teacher_user_id" : message.field;
    const formId = FORM_ID[message.form];
    document.getElementById(formId ?? "")?.querySelector<HTMLElement>(`[name="${name}"]`)?.focus();
  }, [message]);

  const invalidFor = (form: FormName) => (message?.failed && message.form === form ? message.field : null);

  function closeEdit() {
    setEditingId(null);
    lastEditButton.current?.focus();
  }

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
        grade_level: form.get("grade_level") ? Number(form.get("grade_level")) : undefined,
        date_of_birth: form.get("date_of_birth") || undefined,
        assigned_teacher_user_id: form.get("assigned_teacher_user_id") || undefined,
        parent_name: form.get("parent_name") || undefined,
        parent_email: form.get("parent_email") || undefined,
        ...toMasterPayload(form, "create"),
      }),
    }).catch(() => null);
    const data = response ? await response.json().catch(() => ({})) : {};
    setBusy(false);
    if (!response?.ok) {
      setMessage(failure(data, "create"));
      return;
    }
    const parentEmail = String(form.get("parent_email") || "");
    setMessage({ text: `${data.full_name} added to the roster.${parentStatusNote(data.parent_status, parentEmail)}`, failed: false, form: "create" });
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
        grade_level: form.get("grade_level") ? Number(form.get("grade_level")) : null,
        date_of_birth: form.get("date_of_birth") || null,
        assigned_teacher_user_id: form.get("assigned_teacher_user_id") || null,
        parent_name: form.get("parent_name") || undefined,
        parent_email: form.get("parent_email") || undefined,
        ...toMasterPayload(form, "edit"),
      }),
    }).catch(() => null);
    const data = response ? await response.json().catch(() => ({})) : {};
    setBusy(false);
    if (!response?.ok) {
      setMessage(failure(data, "edit"));
      return;
    }
    const parentEmail = String(form.get("parent_email") || "");
    setMessage({ text: `Student updated.${parentStatusNote(data.parent_status, parentEmail)}`, failed: false, form: "roster" });
    closeEdit();
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
    }).catch(() => null);
    const data = response ? await response.json().catch(() => ({})) : {};
    setBusy(false);
    if (!response?.ok) {
      setMessage(failure(data, "link"));
      return;
    }
    setMessage({ text: "Parent linked to this student.", failed: false, form: "roster" });
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
          <p className="muted">
            No students yet. Add one below, or <Link href="/school/coordinator/students/bulk-upload">use bulk upload</Link> for many at once.
          </p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Student ID</th><th>Name</th><th>Grade/Class</th><th>Section</th><th>Roll no.</th><th>Parent</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.id}>
                    <td><code>{s.student_code}</code></td>
                    <td>{s.full_name}</td>
                    <td>{s.grade_or_class || "-"}</td>
                    <td>{s.section || "-"}</td>
                    <td>{s.roll_number || "-"}</td>
                    <td>{s.pending_parent_email ? <span className="status pending">Invite sent to {s.pending_parent_email}</span> : "-"}</td>
                    <td style={{ display: "flex", gap: 8 }}>
                      <button className="btn ghost small" onClick={(e) => { lastEditButton.current = e.currentTarget; setEditingId(s.id); setLinkingId(null); }}>Edit</button>
                      <button className="btn ghost small" onClick={() => { setLinkingId(s.id); setEditingId(null); }}>Link parent</button>
                      {/* QA2-03: this page holds the profile, photo and journey timeline -- name it for what it holds. */}
                      <a className="btn ghost small" href={`/school/coordinator/students/${s.id}`}>Profile &amp; timeline</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {message?.form === "roster" && <FormMessage message={message} />}
      </div>

      {editing && (
        <div className="action-card">
          <h3 id="edit-heading" ref={editHeading} tabIndex={-1}>Edit {editing.full_name} <span className="muted" style={{ fontSize: 13 }}>({editing.student_code})</span></h3>
          {/* key: a different student remounts the form so every defaultValue is that student's. */}
          <form className="form" id={FORM_ID.edit} key={editing.id} aria-busy={busy} onSubmit={(e) => saveEdit(e, editing.id)}>
            <fieldset className="form-busy-wrap" disabled={busy}>
              <SchoolStudentFields idPrefix="edit" student={editing} teachers={teachers} includeInactiveTeachers invalidField={invalidFor("edit")} errorId={ERROR_ID("edit")} />
              <div className="field" style={{ flexDirection: "row", gap: 12 }}>
                <button className="btn">{busy ? "Saving…" : "Save changes"}</button>
                <button type="button" className="btn secondary" onClick={closeEdit}>Cancel</button>
              </div>
            </fieldset>
          </form>
          {message?.form === "edit" && <FormMessage message={message} />}
        </div>
      )}

      {linking && (
        <div className="action-card">
          <h3>Link a parent to {linking.full_name}</h3>
          <form className="form" aria-busy={busy} onSubmit={(e) => linkParent(e, linking.id)}>
            <fieldset className="form-busy-wrap" disabled={busy}>
              <div className="field">
                <label htmlFor="link-parent-email">Parent&apos;s email</label>
                <input id="link-parent-email" name="parent_email" type="email" required />
                <span className="muted" style={{ fontSize: 12 }}>Must already be an accepted Parent account at your own school.</span>
              </div>
              <div className="field" style={{ flexDirection: "row", gap: 12 }}>
                <button className="btn">{busy ? "Linking…" : "Link parent"}</button>
                <button type="button" className="btn secondary" onClick={() => setLinkingId(null)}>Cancel</button>
              </div>
            </fieldset>
          </form>
          {message?.form === "link" && <FormMessage message={message} />}
        </div>
      )}

      <div className="action-card">
        <h3>Add one student</h3>
        <form className="form" id={FORM_ID.create} aria-busy={busy} onSubmit={createStudent}>
          <fieldset className="form-busy-wrap" disabled={busy}>
            <SchoolStudentFields idPrefix="new" teachers={teachers} includeInactiveTeachers={false} invalidField={invalidFor("create")} errorId={ERROR_ID("create")} />
            <button className="btn">{busy ? "Saving…" : "Add student"}</button>
          </fieldset>
        </form>
        {message?.form === "create" && <FormMessage message={message} />}
        <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>Adding many students at once? <Link href="/school/coordinator/students/bulk-upload">Use bulk upload</Link> instead.</p>
      </div>
    </div>
  );
}

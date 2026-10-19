"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { staffFailure } from "@/lib/agentStaff";
import { sendJson } from "@/lib/apiErrors";

export const WALK_IN_URL = "/api/v1/counselor/students";

export type WalkInStudent = { id: string; full_name: string; email: string; phone: string | null; student_code: string | null; setup: "pending_setup" | "link_expired" | null };

const SETUP_LABEL = { pending_setup: "Set-up pending", link_expired: "Link expired" } as const;

// csc-002/csc-003 (DEC-SCOPE-227/228): one walk-in student. While the account is pending (never activated) the counselor can resend the
// set-password link or fix the details; once the student has a password there is nothing to do here. AgentStaffRow's pattern: inline
// edit (Escape/Cancel return focus to Edit), results announced by the panel, refusals (409/429) in the row's status region.
export default function CounselorWalkInStudentRow({ student, onChanged }: { student: WalkInStudent; onChanged: (message: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const returnFocus = useRef(false);
  const editId = `walk-in-edit-${student.id}`;
  const pending = student.setup !== null;

  useEffect(() => {
    if (!editing && returnFocus.current) {
      document.getElementById(editId)?.focus();
      returnFocus.current = false;
    }
  }, [editing, editId]);

  function close() {
    returnFocus.current = true;
    setError(null);
    setEditing(false);
  }

  async function send(path: string, method: "POST" | "PATCH", body: unknown, keepsEntry: boolean, message: (data: Record<string, unknown>) => string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    const outcome = await sendJson(`${WALK_IN_URL}/${student.id}${path}`, method, body);
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) {
      setError(staffFailure(outcome, keepsEntry));
      return;
    }
    returnFocus.current = true;
    setEditing(false);
    onChanged(message(outcome.data));
  }

  const emailed = (data: Record<string, unknown>, to: string) =>
    data.email_status === "sent" ? `A new set-password link was emailed to ${to}.` : "A new set-password link was created, but the email was not delivered. Try Resend link in a minute.";

  function resend() {
    send("/welcome-links", "POST", {}, false, (data) => emailed(data, student.email));
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const entered = { full_name: String(data.get("full_name") ?? "").trim(), email: String(data.get("email") ?? "").trim().toLowerCase(), phone: String(data.get("phone") ?? "").trim() || null };
    const changes = Object.fromEntries(Object.entries(entered).filter(([field, value]) => value !== student[field as keyof typeof entered]));
    if (Object.keys(changes).length === 0) {
      close();
      return;
    }
    send("", "PATCH", changes, true, (result) => {
      const saved = result.student as WalkInStudent;
      return result.email_status === undefined ? `${saved.full_name} updated.` : `${saved.full_name} updated. ${emailed(result, saved.email)}`;
    });
  }

  return (
    <li style={{ padding: "8px 0", borderBottom: "1px solid var(--line, #e5e7eb)", overflowWrap: "anywhere" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", alignItems: "center" }}>
        <strong>{student.full_name}</strong>
        <span>{student.email}</span>
        {student.student_code && <span className="muted">Student ID {student.student_code}</span>}
        <span className="badge">{student.setup ? SETUP_LABEL[student.setup] : "Active"}</span>
      </div>
      {editing && (
        <form className="form" onSubmit={save} onKeyDown={(e) => e.key === "Escape" && close()} aria-label={`Edit ${student.full_name}`} style={{ marginTop: 8 }}>
          <div className="field"><label htmlFor={`${editId}-name`}>Full name</label><input id={`${editId}-name`} name="full_name" defaultValue={student.full_name} maxLength={160} required autoFocus /></div>
          <div className="field"><label htmlFor={`${editId}-email`}>Email</label><input id={`${editId}-email`} name="email" type="email" defaultValue={student.email} maxLength={255} required /></div>
          <div className="field"><label htmlFor={`${editId}-phone`}>Phone (optional)</label><input id={`${editId}-phone`} name="phone" type="tel" defaultValue={student.phone ?? ""} maxLength={40} /></div>
          <p className="muted" style={{ fontSize: 13 }}>Changing the email sends a new link to the new address; the old link stops working.</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            <button type="button" className="btn secondary small" disabled={busy} onClick={close}>Cancel</button>
          </div>
        </form>
      )}
      {pending && !editing && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
          <button id={editId} type="button" className="btn secondary small" aria-label={`Edit ${student.full_name}`} onClick={() => setEditing(true)}>Edit</button>
          <button type="button" className="btn secondary small" aria-label={`Resend link to ${student.full_name}`} disabled={busy} onClick={resend}>{busy ? "Sending…" : "Resend link"}</button>
        </div>
      )}
      {/* Always mounted so screen readers announce a refusal when it arrives; styled only while it has something to say. */}
      <div className={error ? "form-error" : undefined} role="status" aria-live="polite" style={error ? { marginTop: 8, fontSize: 13 } : undefined}>{error}</div>
    </li>
  );
}

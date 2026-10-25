"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useId, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import { ARCHIVE_REASON_MAX, studentArchiveUrl, type StudentArchive } from "@/lib/overseasStudent360";

/** ccrm-040 (DEC-SCOPE-275 AR1-AR7): the student 360's archive state. An archived student shows a banner (the Overseas Admin may
 *  restore); otherwise the student's counselor or the Admin may archive with a reason. The server holds every rule (an open application
 *  is a 409 naming it), so its message is shown as it comes. */
export default function StudentArchiveControls({ studentId, archive, permissions }: {
  studentId: string; archive: StudentArchive | null; permissions: { archive: boolean; restore: boolean };
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reasonId = useId();

  async function send(action: "archive" | "restore", body: unknown) {
    setBusy(true);
    setError(null);
    const result = await sendJson(studentArchiveUrl(studentId, action), "POST", body);
    setBusy(false);
    if (!result.ok) return setError(result.message);
    setOpen(false);
    setReason("");
    router.refresh();
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (reason.trim().length < 3) return setError("Give a reason of at least 3 characters.");
    void send("archive", { reason: reason.trim() });
  }

  const alert = error && <p className="form-error" role="alert" style={{ margin: "8px 0 0" }}>{error}</p>;
  if (archive) {
    return (
      <div className="card" role="status" style={{ borderLeft: "4px solid var(--amber)" }}>
        <strong>Archived</strong>
        <p style={{ margin: "4px 0 0" }}>
          <LocalTime value={archive.archived_at} />{archive.archived_by && <> by {archive.archived_by}</>}. Reason: {archive.reason}
        </p>
        <p className="muted" style={{ margin: "4px 0 0" }}>
          The student and their applications are hidden from the working lists. {permissions.restore ? "" : "Only the Overseas Admin can restore them."}
        </p>
        {permissions.restore && (
          <button type="button" className="btn secondary small" style={{ marginTop: 8 }} disabled={busy} onClick={() => void send("restore", {})}>
            {busy ? "Restoring…" : "Restore student"}
          </button>
        )}
        {alert}
      </div>
    );
  }
  if (!permissions.archive) return null;
  if (!open) {
    return (
      <p style={{ margin: 0 }}>
        <button type="button" className="btn secondary small" onClick={() => { setOpen(true); setError(null); }}>Archive student</button>
      </p>
    );
  }
  return (
    <form className="card" onSubmit={submit} noValidate>
      <h2>Archive this student</h2>
      <p className="muted">Archive a student whose applications are all closed or enrolled. Nothing is deleted; the Overseas Admin can restore them.</p>
      <div className="field">
        <label htmlFor={reasonId}>Reason</label>
        <textarea id={reasonId} value={reason} maxLength={ARCHIVE_REASON_MAX} rows={3} required onChange={(e) => setReason(e.target.value)} />
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Archiving…" : "Archive student"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={() => { setOpen(false); setError(null); }}>Cancel</button>
      </div>
      {alert}
    </form>
  );
}

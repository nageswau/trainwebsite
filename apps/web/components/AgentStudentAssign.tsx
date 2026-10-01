"use client";

import { useEffect, useRef, useState } from "react";

import { detailMessage } from "@/lib/apiErrors";
import { AgentStudentDetail, AgentStudentItem, RECORDS_URL } from "@/lib/agentStudents";
import { STAFF_URL, StaffMember } from "@/lib/agentStaff";

// AGN-004 (DEC-SCOPE-041, spec §6, AC09): a Master assigns a student to one of the agency's active Staff members, or unassigns.
// The staff list is fetched each time the choice opens, so a member deactivated meanwhile is never offered (G5); the server
// still refuses any target that is not an active Staff member of this agency. Inline, like the archive confirmation.
export default function AgentStudentAssign({ student, onAssigned }: { student: AgentStudentItem; onAssigned: (s: AgentStudentDetail) => void }) {
  const current = student.assigned_to?.id ?? "";
  const [open, setOpen] = useState(false);
  const [staff, setStaff] = useState<StaffMember[] | null>(null);
  const [choice, setChoice] = useState(current);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  const focusOpener = useRef(false);

  useEffect(() => {
    if (!open && focusOpener.current) {
      focusOpener.current = false;
      opener.current?.focus();
    }
  }, [open]);

  async function loadStaff() {
    setError(null);
    setStaff(null);
    try {
      const response = await fetch(`${STAFF_URL}?limit=100`);
      const body = await response.json().catch(() => null);
      if (!response.ok || !Array.isArray(body?.items)) return setError("Couldn't load your staff.");
      setStaff((body.items as StaffMember[]).filter((m) => m.status === "active"));
    } catch {
      setError("Couldn't load your staff.");
    }
  }

  function start() {
    setChoice(current);
    setOpen(true);
    loadStaff();
  }

  function close() {
    focusOpener.current = true;
    setOpen(false);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${RECORDS_URL}/${student.id}/assign`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ member_id: choice || null }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || !body?.student) return setError(detailMessage(body?.detail, "Unable to assign this student."));
      close();
      onAssigned(body.student);
    } catch {
      setError("Network error. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button ref={opener} type="button" className="btn secondary small" aria-label={`Assign ${student.full_name}`} onClick={start}>
        Assign
      </button>
    );
  }

  const selectId = `agent-student-assign-${student.id}`;
  return (
    <div role="group" aria-label={`Assign ${student.full_name}`} style={{ flexBasis: "100%" }}>
      <div className="field" style={{ margin: 0 }}>
        <label htmlFor={selectId}>Assign to</label>
        <select id={selectId} value={choice} disabled={staff === null || busy} autoFocus onChange={(e) => setChoice(e.target.value)}>
          <option value="">Unassigned</option>
          {/* A deactivated assignee keeps the student (G5) but cannot be chosen again. */}
          {staff && student.assigned_to && !staff.some((m) => m.id === current) && (
            <option value={current} disabled>
              {student.assigned_to.code} · {student.assigned_to.full_name} (deactivated)
            </option>
          )}
          {staff?.map((m) => (
            <option key={m.id} value={m.id}>
              {m.code} · {m.full_name}
            </option>
          ))}
        </select>
      </div>
      {staff === null && !error && (
        <p className="muted" style={{ fontSize: 13 }}>
          Loading staff…
        </p>
      )}
      {error && (
        <p className="form-error" role="alert" style={{ fontSize: 13 }}>
          {error}{" "}
          {staff === null && (
            <button type="button" className="btn secondary small" aria-label="Retry loading staff" onClick={loadStaff}>
              Retry
            </button>
          )}
        </p>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
        <button type="button" className="btn small" disabled={staff === null || busy || choice === current} onClick={save}>
          {busy ? "Saving…" : "Save assignment"}
        </button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={close}>
          Cancel
        </button>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";

import AgentShortlistPanel from "./AgentShortlistPanel";
import AgentStudentCounselingCard from "./AgentStudentCounselingCard";
import AgentStudentForm from "./AgentStudentForm";
import AgentTasksBlock from "./AgentTasksBlock";
import { AgentStudentDetail, assignedText } from "@/lib/agentStudents";

export { assignedText }; // AGN-016: moved to lib/agentStudents (the task card shares it); re-exported for existing importers

// AGN-004 (spec §6, F5): one student's full record beside the list -- no separate route. A student with a login shows the details
// from their own account and is not edited here (F2); an archived student is read-only until a Master unarchives them.
export default function AgentStudentDetailPanel({
  detail,
  onClose,
  onSaved,
  onDirtyChange,
}: {
  detail: AgentStudentDetail;
  onClose: () => void;
  onSaved: (s: AgentStudentDetail, notice?: string) => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  // One form at a time (AGN-006): the Step 1 edit replaces the details; counseling edits inside its own section.
  const [editing, setEditing] = useState<"none" | "student" | "counseling">("none");
  const headingId = `agent-student-detail-${detail.id}`;

  useEffect(() => {
    document.getElementById(headingId)?.focus();
  }, [headingId]);

  const rows: [string, string | number | null][] = [
    ["Login", detail.has_login ? "Has login (details come from the student's own account)" : "No login"],
    ["Email", detail.email],
    ["Phone", detail.phone],
    ["Date of birth", detail.date_of_birth],
    ["Highest qualification", detail.highest_qualification],
    ["Institution", detail.institution],
    ["Graduation year", detail.graduation_year],
    ["Preferred country", detail.preferred_country],
    ["Preferred course", detail.preferred_course],
    ["Preferred intake", detail.preferred_intake],
    ["Notes", detail.notes],
    ["Assigned to", assignedText(detail.assigned_to)],
    ["Created by", detail.created_by],
    ...(detail.status === "archived" ? ([["Archived by", detail.archived_by]] as [string, string | null][]) : []),
  ];

  return (
    <section
      className="card"
      aria-labelledby={headingId}
      style={{ marginTop: 16 }}
      onKeyDown={(e) => {
        if (e.key === "Escape" && editing === "none") onClose();
      }}
    >
      <h4 id={headingId} tabIndex={-1}>
        {detail.full_name}
      </h4>
      {editing === "student" ? (
        <AgentStudentForm
          mode="edit"
          student={detail}
          onCancel={() => setEditing("none")}
          onSaved={(s) => {
            setEditing("none");
            onSaved(s);
            // The form (and its focused Save button) unmounts: put keyboard focus back on this record.
            requestAnimationFrame(() => document.getElementById(headingId)?.focus());
          }}
        />
      ) : (
        <>
          <dl className="record-details">
            {rows.map(([label, value]) => (
              <div key={label} style={{ display: "contents" }}>
                <dt>{label}</dt>
                <dd style={label === "Notes" ? { whiteSpace: "pre-wrap" } : undefined}>{value === null || value === "" ? "—" : value}</dd>
              </div>
            ))}
          </dl>
          {editing === "none" && !detail.has_login && detail.status === "active" && (
            <button type="button" className="btn small" onClick={() => setEditing("student")}>
              Edit
            </button>
          )}
          <AgentStudentCounselingCard
            detail={detail}
            editing={editing === "counseling"}
            onEditingChange={(open) => setEditing(open ? "counseling" : "none")}
            onSaved={(s) => onSaved(s, `Counseling saved for ${s.full_name}.`)}
            onDirtyChange={onDirtyChange}
            onStale={(s) => onSaved(s, `${s.full_name} has been archived.`)}
          />
          {/* AGN-007 (DEC-SCOPE-049): the student's university shortlist; one form at a time (AGN-006), so hidden while counseling is edited. */}
          {editing === "none" && (
            <AgentShortlistPanel studentId={detail.id} archived={detail.status === "archived"} onStudentGone={onClose} onStudentChanged={onClose} />
          )}
          {/* AGN-016 (DEC-SCOPE-051): the student's tasks, open first; read-only when archived. */}
          {editing === "none" && (
            <section aria-labelledby={`tasks-${detail.id}`} style={{ marginTop: 16 }}>
              <h5 id={`tasks-${detail.id}`} style={{ fontSize: "18px", margin: "0 0 8px" }}>Tasks</h5>
              <AgentTasksBlock view="all" studentId={detail.id} archived={detail.status === "archived"} Heading="h6" />
            </section>
          )}
          {editing === "none" && (
            <button type="button" className="btn secondary small" onClick={onClose} style={{ marginTop: 16 }}>
              Close
            </button>
          )}
        </>
      )}
    </section>
  );
}

"use client";

import { useEffect, useState } from "react";

import AgentStudentForm from "./AgentStudentForm";
import { AgentStudentDetail, AgentStudentItem } from "@/lib/agentStudents";

export function assignedText(a: AgentStudentItem["assigned_to"]): string {
  return a ? `${a.code} · ${a.full_name}${a.status !== "active" ? " (deactivated)" : ""}` : "Unassigned";
}

// AGN-004 (spec §6, F5): one student's full record beside the list -- no separate route. A student with a login shows the details
// from their own account and is not edited here (F2); an archived student is read-only until a Master unarchives them.
export default function AgentStudentDetailPanel({
  detail,
  onClose,
  onSaved,
}: {
  detail: AgentStudentDetail;
  onClose: () => void;
  onSaved: (s: AgentStudentDetail) => void;
}) {
  const [editing, setEditing] = useState(false);
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
        if (e.key === "Escape" && !editing) onClose();
      }}
    >
      <h4 id={headingId} tabIndex={-1}>
        {detail.full_name}
      </h4>
      {editing ? (
        <AgentStudentForm
          mode="edit"
          student={detail}
          onCancel={() => setEditing(false)}
          onSaved={(s) => {
            setEditing(false);
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
          {!detail.has_login && detail.status === "active" && (
            <button type="button" className="btn small" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}{" "}
          <button type="button" className="btn secondary small" onClick={onClose}>
            Close
          </button>
        </>
      )}
    </section>
  );
}

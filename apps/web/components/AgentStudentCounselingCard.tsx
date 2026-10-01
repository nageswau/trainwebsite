"use client";

import type { ReactNode } from "react";

import AgentStudentCounselingForm from "./AgentStudentCounselingForm";
import LocalTime from "./LocalTime";
import { refocus } from "@/lib/focus";
import { AgentStudentDetail, formatBudget } from "@/lib/agentStudents";

// When and by whom; the date in the viewer's zone (the date sweep rule -- server UTC and browser must not disagree).
function stamp(at: string | null, by: string | null): ReactNode {
  return (
    <>
      {at && <LocalTime value={at} />}
      {at && by ? ", " : null}
      {by ? `by ${by}` : null}
    </>
  );
}

// AGN-006 (DEC-SCOPE-048): the student's counseling record (EVID-015 §5 Step 2) under the AGN-004 details. It arrives with the
// detail -- no fetch of its own. Recorded only for an active student with no login (C4); everything is rendered as text.
export default function AgentStudentCounselingCard({
  detail,
  editing,
  onEditingChange,
  onSaved,
  onDirtyChange,
}: {
  detail: AgentStudentDetail;
  editing: boolean;
  onEditingChange: (open: boolean) => void;
  onSaved: (s: AgentStudentDetail) => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const c = detail.counseling ?? null;
  const headingId = `counseling-heading-${detail.id}`;
  const openerId = `counseling-open-${detail.id}`;
  const editable = !detail.has_login && detail.status === "active";

  const rows: [string, ReactNode][] = c
    ? [
        ["Counseling completed", c.counseling_completed ? <>Yes — {stamp(c.completed_at, c.completed_by)}</> : "No"],
        ["Career interest", c.career_interest],
        ["Course preference", c.course_preference],
        ["Country preference", c.country_preference],
        ["Budget", c.budget_amount === null ? null : formatBudget(c.budget_amount, c.budget_currency)],
        ["Remarks", c.remarks],
        ["Last updated", stamp(c.updated_at, c.updated_by)],
      ]
    : [];

  return (
    <section aria-labelledby={headingId} style={{ marginTop: 16 }}>
      <h5 id={headingId} tabIndex={-1}>
        Counseling
      </h5>
      {editing ? (
        <AgentStudentCounselingForm
          detail={detail}
          onDirtyChange={onDirtyChange}
          onCancel={() => {
            onEditingChange(false);
            refocus(openerId);
          }}
          onSaved={(s) => {
            onEditingChange(false);
            onSaved(s);
            refocus(headingId);
          }}
        />
      ) : (
        <>
          {c ? (
            <dl className="record-details">
              {rows.map(([label, value]) => (
                <div key={label} style={{ display: "contents" }}>
                  <dt>{label}</dt>
                  <dd style={label === "Remarks" ? { whiteSpace: "pre-wrap" } : undefined}>{value === null || value === "" ? "—" : value}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="muted">{detail.has_login ? "Counseling is recorded only for students without a login." : "Counseling not recorded yet."}</p>
          )}
          {editable && (
            <button id={openerId} type="button" className="btn small" onClick={() => onEditingChange(true)}>
              {c ? "Edit counseling" : "Record counseling"}
            </button>
          )}
        </>
      )}
    </section>
  );
}

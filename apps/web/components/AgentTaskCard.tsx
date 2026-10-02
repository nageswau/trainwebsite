"use client";

import LocalTime from "./LocalTime";
import { assignedText } from "@/lib/agentStudents";
import type { AgentTask } from "@/lib/agentTasks";

// AGN-016 (DEC-SCOPE-051): one task. State is always a word (Overdue / Open / Done / Cancelled), never colour alone. The cancel
// confirm puts focus on the safe choice; Escape closes only the confirm (the student detail panel closes on Escape too).
export const doneId = (id: string) => `task-done-${id}`;
export const editId = (id: string) => `task-edit-${id}`;
export const cancelId = (id: string) => `task-cancel-${id}`;

function StatusPill({ t }: { t: AgentTask }) {
  if (t.status === "open") return t.overdue ? <span className="status error">Overdue</span> : <span className="status pending">Open</span>;
  return t.status === "done" ? <span className="status">Done</span> : <span className="status closed">Cancelled</span>;
}

export default function AgentTaskCard({ t, Heading, actionable, busy, confirming, onDone, onEdit, onAskCancel, onKeep, onCancel }: {
  t: AgentTask;
  Heading: "h3" | "h6";
  actionable: boolean;
  busy: boolean;
  confirming: boolean;
  onDone: () => void;
  onEdit: () => void;
  onAskCancel: () => void;
  onKeep: () => void;
  onCancel: () => void;
}) {
  const headingId = `task-${t.id}`;
  return (
    <li className="card" aria-labelledby={headingId} style={{ padding: 16 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 8, justifyContent: "space-between" }}>
        <Heading id={headingId} style={{ fontSize: 17, margin: 0, overflowWrap: "anywhere" }}>{t.title}</Heading>
        <StatusPill t={t} />
      </div>
      <dl className="record-details">
        <dt>Student</dt>
        <dd>{t.student.full_name}{t.student.status === "archived" && " (archived)"}</dd>
        <dt>Due</dt>
        <dd><LocalTime value={t.due_at} time label /></dd>
        <dt>Assigned to</dt>
        <dd>{assignedText(t.assigned_to)}</dd>
        {t.application && (<><dt>Application</dt><dd>{t.application.university ?? "—"}</dd></>)}
        {t.notes && (<><dt>Notes</dt><dd style={{ whiteSpace: "pre-wrap" }}>{t.notes}</dd></>)}
        {t.closed_at && (<><dt>{t.status === "done" ? "Completed" : "Cancelled"}</dt><dd>{t.closed_by ?? "—"}, <LocalTime value={t.closed_at} time label /></dd></>)}
      </dl>
      {/* QA16-03: an archived student's open task has no actions -- say why, as the student card does. */}
      {t.status === "open" && t.student.status === "archived" && <p className="muted" style={{ margin: "8px 0 0" }}>The student is archived, so this task is read-only.</p>}
      {actionable && t.status === "open" && (
        <div className="actions" style={{ marginTop: 12, gap: 8 }}>
          {confirming ? (
            <span
              role="group"
              aria-label={`Confirm cancelling “${t.title}”`}
              style={{ display: "flex", flexWrap: "wrap", gap: 8 }}
              onKeyDown={(k) => {
                if (k.key === "Escape") {
                  k.stopPropagation();
                  onKeep();
                }
              }}
            >
              <button type="button" className="btn small" disabled={busy} onClick={onCancel}>Confirm cancel</button>
              {/* Focus lands here (the safe choice) when the confirm opens. */}
              <button type="button" className="btn secondary small" autoFocus onClick={onKeep}>Keep task</button>
            </span>
          ) : (
            <>
              <button id={doneId(t.id)} type="button" className="btn small" disabled={busy} aria-label={`Mark “${t.title}” done`} onClick={onDone}>Mark done</button>
              <button id={editId(t.id)} type="button" className="btn secondary small" disabled={busy} aria-label={`Edit “${t.title}”`} onClick={onEdit}>Edit</button>
              <button id={cancelId(t.id)} type="button" className="btn ghost small" disabled={busy} aria-label={`Cancel “${t.title}”`} onClick={onAskCancel}>Cancel task</button>
            </>
          )}
        </div>
      )}
    </li>
  );
}

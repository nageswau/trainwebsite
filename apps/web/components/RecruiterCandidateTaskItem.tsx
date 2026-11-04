"use client";
import Link from "next/link";
import { useId, useRef, useState } from "react";

import RecruiterCandidateTaskForm from "@/components/RecruiterCandidateTaskForm";
import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendRequest } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { CANDIDATES_PATH, personLabel } from "@/lib/recruiterCandidates";
import { isCandidateTask, taskTypeLabel, taskUrl, type CandidateTask } from "@/lib/recruiterCandidateTasks";
import { RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";

const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;

/** hrc-016 (T5/T6): one candidate task with Done, Edit and Cancel task -- offered only when the API says so (`can_change`). `card` is the
 *  My tasks form (the candidate first, linked). A refusal (changed elsewhere: 403/404/409) is handed up so the list reloads. */
export default function RecruiterCandidateTaskItem({ task, card = false, onChanged, onRefused }: {
  task: CandidateTask; card?: boolean; onChanged: (task: CandidateTask, notice: string) => void; onRefused: (message: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const sending = useRef(false);
  const id = useId();

  async function act(action: "complete" | "cancel", notice: string) {
    if (sending.current) return; // a double click sends once
    if (action === "cancel" && !window.confirm(`Cancel the task "${task.title}"?`)) return;
    sending.current = true;
    setBusy(true);
    setFailure(null);
    setSessionEnded(false);
    const result = await sendRequest(taskUrl(task.id, action), { method: "POST" });
    sending.current = false;
    setBusy(false);
    if (result.ok) return isCandidateTask(result.data) ? onChanged(result.data, notice) : setFailure(SAVE_FAILED);
    const kind = writeFailure(result.status);
    if (kind === "changed") return onRefused(result.message);
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message);
  }

  const facts = [
    ["Type", taskTypeLabel(task.task_type)],
    ["Due", formatSchoolDateTime(task.due_at, true)],
    ["Assigned to", personLabel(task.assignee)],
    task.requirement && ["Requirement", `${task.requirement.code ? `${task.requirement.code} — ` : ""}${task.requirement.title}`],
  ].filter(Boolean) as [string, string][];
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-title`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong id={`${id}-title`} style={{ overflowWrap: "anywhere" }}>
          {card ? (
            <><Link href={`${CANDIDATES_PATH}/${encodeURIComponent(task.candidate.id)}`} style={LINK_STYLE}>{task.candidate.name}</Link>{" "}
              <span className="muted" style={{ fontWeight: 400 }}>{task.candidate.candidate_code}</span> · {task.title}</>
          ) : task.title}
        </strong>
        {task.overdue && <span className="badge status error">Overdue</span>}
        {task.status === "done" && <span className="badge">Done</span>}
        {task.status === "cancelled" && <span className="badge">Cancelled</span>}
      </div>
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))", gap: "4px 16px", margin: 0 }}>
        {facts.map(([term, value]) => (
          <div key={term}>
            <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
            <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
          </div>
        ))}
      </dl>
      {task.notes && <p style={{ ...TEXT, margin: 0 }}>{task.notes}</p>}
      {task.completed_at && <p className="muted" style={{ margin: 0 }}>Done {formatSchoolDateTime(task.completed_at)}{task.completed_by && ` by ${task.completed_by.full_name}`}</p>}
      {task.cancelled_at && <p className="muted" style={{ margin: 0 }}>Cancelled {formatSchoolDateTime(task.cancelled_at)}{task.cancelled_by && ` by ${task.cancelled_by.full_name}`}</p>}
      {editing && (
        <RecruiterCandidateTaskForm candidateId={task.candidate.id} task={task} onCancel={() => setEditing(false)}
          onSaved={(next) => { setEditing(false); onChanged(next, "Task updated."); }} />
      )}
      {!editing && task.can_change && (
        <div className="actions">
          <button type="button" className="btn small" disabled={busy} onClick={() => void act("complete", "Task marked done.")}>Done</button>
          <button type="button" className="btn secondary small" disabled={busy} onClick={() => setEditing(true)}>Edit</button>
          <button type="button" className="btn secondary small" disabled={busy} onClick={() => void act("cancel", "Task cancelled.")}>Cancel task</button>
        </div>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {sessionEnded && (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref={RECRUITER_SIGN_IN} />
        </div>
      )}
    </li>
  );
}

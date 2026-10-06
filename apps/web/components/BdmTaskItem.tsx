"use client";
import Link from "next/link";
import { useState } from "react";

import BdmAppointmentReasonForm from "@/components/BdmAppointmentReasonForm";
import BdmTaskForm from "@/components/BdmTaskForm";
import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { daysOverdue, isTask, KIND_LABEL, orgTypeText, SAVE_FAILED, SESSION_ENDED, type Task, taskUrl, writeFailure } from "@/lib/bdmTasks";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";
import { BDM_SIGN_IN } from "@/lib/navigation";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// Typed text keeps its line breaks and wraps even an unbroken word, so it never widens the page (QA8-01).
const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;
// The detail line's links are tap targets of at least 24px (WCAG 2.2 SC 2.5.8; QA8B-07).
const META_LINK = { ...LINK_STYLE, display: "inline-block", minHeight: 24, lineHeight: "24px" } as const;

// bdm-008 (spec §9): one follow-up or task. Actions render from `permissions` only -- the server enforces every rule. A refused write
// (409/403/404) goes to the list, which says why and reloads; anything else keeps the row as it was and says so here (QA8B-01/02).
export default function BdmTaskItem({ task, today, basePath, showAssignee, onChanged, onRefused }: {
  task: Task; today: string; basePath: "/bdm" | "/bdm/manager"; showAssignee: boolean;
  onChanged: (task: Task, notice: string) => void; onRefused: (message: string) => void;
}) {
  const [mode, setMode] = useState<"view" | "edit" | "cancel">("view");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const p = task.permissions;
  const focus = useFocusAfterRender();
  const editId = `task-${task.id}-edit`;
  const cancelId = `task-${task.id}-cancel`;
  const close = (id: string) => { setMode("view"); focus(id); }; // the button that opened the form is back (QA8-02)

  async function act(path: "complete" | "cancel", body: unknown, notice: string) {
    setBusy(true);
    setFailure(null);
    setSessionEnded(false);
    const result = await sendJson(`${taskUrl(task.id)}/${path}`, "POST", body);
    setBusy(false);
    if (result.ok) return isTask(result.data) ? onChanged(result.data, notice) : setFailure(SAVE_FAILED);
    const kind = writeFailure(result.status);
    if (kind === "changed") return onRefused(result.message);
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message); // invalid: the server's words; offline: NOT_COMPLETED
  }

  const due = formatCalendarDate(task.due_on);
  return (
    <li className="action-card" style={{ listStyle: "none" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong style={{ overflowWrap: "anywhere" }}>{task.title}</strong>
        <span className="badge">{KIND_LABEL[task.kind]}</span>
        {task.overdue && <span className="badge status error">Overdue · {daysOverdue(task.due_on, today)} days</span>}
      </div>
      <p className="muted" style={{ margin: "4px 0", display: "flex", flexWrap: "wrap", gap: 8 }}>
        <span>Due {due}</span>
        {task.organization ? (
          <span>
            <Link href={`${basePath}/organizations/${task.organization.id}`} style={META_LINK}>{task.organization.name}</Link>
            {" · "}<span>{orgTypeText(task.organization.org_type)}</span>
            {task.organization.archived && <> <span className="badge">Archived</span></>}
          </span>
        ) : <span>{orgTypeText(null)}</span>}
        {task.appointment ? (
          <Link href={`${basePath}/appointments/${task.appointment.id}`} style={META_LINK}>From {task.appointment.code}</Link>
        ) : task.source === "manual" && <span>Added by hand</span>}
        {showAssignee && <span>{task.assignee.full_name}{!task.assignee.active && " (inactive)"}</span>}
      </p>
      {task.notes && <p style={{ ...TEXT, margin: "4px 0" }}>{task.notes}</p>}
      {task.completed_at && <p className="muted" style={{ margin: 0 }}>Done {formatSchoolDateTime(task.completed_at)}</p>}
      {task.cancelled_at && (
        <p className="muted" style={{ ...TEXT, margin: 0 }}>Cancelled {formatSchoolDateTime(task.cancelled_at)}{task.cancel_reason && ` — ${task.cancel_reason}`}</p>
      )}
      {mode === "edit" && <BdmTaskForm task={task} onSaved={(t) => { setMode("view"); onChanged(t, "Changes saved."); }} onCancel={() => close(editId)} />}
      {mode === "cancel" && (
        <BdmAppointmentReasonForm label="Cancel task" submitText="Cancel it" busyText="Cancelling…" busy={busy}
          onSubmit={(reason) => void act("cancel", { reason }, "Cancelled.")} onCancel={() => close(cancelId)} />
      )}
      {mode === "view" && (p.can_complete || p.can_edit || p.can_cancel) && (
        <div className="actions">
          {p.can_complete && <button type="button" className="btn small" disabled={busy} onClick={() => void act("complete", undefined, "Marked done.")}>{busy ? "Saving…" : "Done"}</button>}
          {p.can_edit && <button id={editId} type="button" className="btn secondary small" disabled={busy} onClick={() => setMode("edit")}>Edit</button>}
          {p.can_cancel && <button id={cancelId} type="button" className="btn secondary small" disabled={busy} onClick={() => setMode("cancel")}>Cancel task</button>}
        </div>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {sessionEnded && (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref={BDM_SIGN_IN} />
        </div>
      )}
    </li>
  );
}

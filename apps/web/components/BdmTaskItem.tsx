"use client";
import Link from "next/link";
import { useState } from "react";

import BdmAppointmentReasonForm from "@/components/BdmAppointmentReasonForm";
import BdmTaskForm from "@/components/BdmTaskForm";
import { sendJson } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { daysOverdue, isTask, KIND_LABEL, orgTypeText, type Task, taskUrl } from "@/lib/bdmTasks";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";

// bdm-008 (spec §9): one follow-up or task. Actions render from `permissions` only -- the server enforces every rule. A refused write
// (409/403/404) goes to the list, which says why and reloads; a dropped network keeps the row as it was with the message.
export default function BdmTaskItem({ task, today, basePath, showAssignee, onChanged, onRefused }: {
  task: Task; today: string; basePath: "/bdm" | "/bdm/manager"; showAssignee: boolean;
  onChanged: (task: Task, notice: string) => void; onRefused: (message: string) => void;
}) {
  const [mode, setMode] = useState<"view" | "edit" | "cancel">("view");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const p = task.permissions;

  async function act(path: "complete" | "cancel", body: unknown, notice: string) {
    setBusy(true);
    setFailure(null);
    const result = await sendJson(`${taskUrl(task.id)}/${path}`, "POST", body);
    setBusy(false);
    if (result.ok && isTask(result.data)) return onChanged(result.data, notice);
    if (!result.ok && result.status) return onRefused(result.message);
    setFailure(result.ok ? "That didn't save. Try again." : result.message);
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
            <Link href={`${basePath}/organizations/${task.organization.id}`} style={LINK_STYLE}>{task.organization.name}</Link>
            {" · "}<span>{orgTypeText(task.organization.org_type)}</span>
            {task.organization.archived && <> <span className="badge">Archived</span></>}
          </span>
        ) : <span>{orgTypeText(null)}</span>}
        {task.appointment ? (
          <Link href={`${basePath}/appointments/${task.appointment.id}`} style={LINK_STYLE}>From {task.appointment.code}</Link>
        ) : task.source === "manual" && <span>Added by hand</span>}
        {showAssignee && <span>{task.assignee.full_name}{!task.assignee.active && " (inactive)"}</span>}
      </p>
      {task.notes && <p style={{ whiteSpace: "pre-wrap", margin: "4px 0" }}>{task.notes}</p>}
      {task.completed_at && <p className="muted" style={{ margin: 0 }}>Done {formatSchoolDateTime(task.completed_at)}</p>}
      {task.cancelled_at && (
        <p className="muted" style={{ margin: 0, whiteSpace: "pre-wrap" }}>Cancelled {formatSchoolDateTime(task.cancelled_at)}{task.cancel_reason && ` — ${task.cancel_reason}`}</p>
      )}
      {mode === "edit" && <BdmTaskForm task={task} onSaved={(t) => { setMode("view"); onChanged(t, "Changes saved."); }} onCancel={() => setMode("view")} />}
      {mode === "cancel" && (
        <BdmAppointmentReasonForm label="Cancel task" submitText="Cancel it" busyText="Cancelling…" busy={busy}
          onSubmit={(reason) => void act("cancel", { reason }, "Cancelled.")} onCancel={() => setMode("view")} />
      )}
      {mode === "view" && (p.can_complete || p.can_edit || p.can_cancel) && (
        <div className="actions">
          {p.can_complete && <button type="button" className="btn small" disabled={busy} onClick={() => void act("complete", undefined, "Marked done.")}>{busy ? "Saving…" : "Done"}</button>}
          {p.can_edit && <button type="button" className="btn secondary small" onClick={() => setMode("edit")}>Edit</button>}
          {p.can_cancel && <button type="button" className="btn secondary small" onClick={() => setMode("cancel")}>Cancel task</button>}
        </div>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
    </li>
  );
}

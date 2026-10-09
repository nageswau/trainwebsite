"use client";
import Link from "next/link";
import { type FormEvent, useId, useState } from "react";

import BdmAppointmentReasonForm from "@/components/BdmAppointmentReasonForm";
import PartnershipTaskForm from "@/components/PartnershipTaskForm";
import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson } from "@/lib/apiErrors";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";
import { BAND_LABEL, type Band, KIND_LABEL, type PartnershipTask, PRIORITY_LABEL, SOURCE_LABEL, taskUrl, taskOf } from "@/lib/partnershipTasks";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { indiaToday } from "@/lib/visits";

// Typed text keeps its line breaks and wraps even an unbroken word, so it never widens the page (bdm-008 QA8-01).
const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;

// upc-020: one follow-up or task. Actions render from `permissions` only -- the server enforces every rule (TK11/TK12). A write the
// server refuses because the task changed (403/404/409) goes to the list, which says why and reloads; anything else stays on the row.
export default function PartnershipTaskItem({ task, showUniversity, canAssign = false, onChanged, onRefused }: {
  task: PartnershipTask; showUniversity: boolean; canAssign?: boolean; onChanged: (task: PartnershipTask, notice: string) => void; onRefused: (message: string) => void;
}) {
  const [mode, setMode] = useState<"view" | "edit" | "reschedule" | "cancel">("view");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [due, setDue] = useState(task.due_on);
  const p = task.permissions;
  const focus = useFocusAfterRender();
  const dueId = useId();
  const ids = { edit: `task-${task.id}-edit`, reschedule: `task-${task.id}-reschedule`, cancel: `task-${task.id}-cancel` };
  const close = (id: string) => { setMode("view"); setFailure(null); focus(id); }; // focus returns to the button that opened the form

  async function act(path: "complete" | "reschedule" | "cancel", body: unknown, notice: string) {
    setBusy(true);
    setFailure(null);
    setSessionEnded(false);
    const result = await sendJson(taskUrl(task.id, path), "POST", body);
    setBusy(false);
    if (result.ok) {
      const saved = taskOf(result.data);
      if (!saved) return setFailure(SAVE_FAILED);
      setMode("view");
      return onChanged(saved, notice);
    }
    const kind = writeFailure(result.status);
    if (kind === "changed") return onRefused(result.message);
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message); // invalid: the server's words; offline: the network message
  }

  const reschedule = (event: FormEvent) => {
    event.preventDefault();
    if (!due) return setFailure("Choose a due date");
    void act("reschedule", { due_on: due }, "Rescheduled.");
  };
  const band = task.band as Band;
  return (
    <li className="action-card" style={{ listStyle: "none" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong style={{ overflowWrap: "anywhere" }}>{task.title}</strong>
        <span className={`badge${task.overdue ? " status error" : ""}`}>{BAND_LABEL[band] ?? task.band}</span>
        <span className="badge">{KIND_LABEL[task.kind]}</span>
        <span className="badge">{PRIORITY_LABEL[task.priority] ?? task.priority} priority</span>
      </div>
      <p className="muted" style={{ margin: "4px 0", display: "flex", flexWrap: "wrap", gap: 8 }}>
        <span>Due {formatCalendarDate(task.due_on)}</span>
        {showUniversity && (
          <Link href={`/partnership/universities/${task.university.id}`} style={{ display: "inline-block", minHeight: 24, lineHeight: "24px" }}>{task.university.name}</Link>
        )}
        <span>Owner: {task.assignee.full_name}{!task.assignee.active && " (inactive)"}</span>
        <span>{SOURCE_LABEL[task.source] ?? task.source}</span>
      </p>
      {task.notes && <p style={{ ...TEXT, margin: "4px 0" }}>{task.notes}</p>}
      {task.completed_at && <p className="muted" style={{ margin: 0 }}>Done {formatSchoolDateTime(task.completed_at)}</p>}
      {task.cancelled_at && (
        <p className="muted" style={{ ...TEXT, margin: 0 }}>Cancelled {formatSchoolDateTime(task.cancelled_at)}{task.cancel_reason && ` — ${task.cancel_reason}`}</p>
      )}
      {mode === "edit" && (
        <PartnershipTaskForm task={task} canAssign={canAssign} onSaved={(t) => { setMode("view"); onChanged(t, "Changes saved."); }} onCancel={() => close(ids.edit)} />
      )}
      {mode === "reschedule" && (
        <form aria-label="Reschedule" className="action-card" noValidate onSubmit={reschedule} onKeyDown={(e) => e.key === "Escape" && close(ids.reschedule)}>
          <div className="field">
            <label htmlFor={dueId}>New due date (IST)</label>
            <input id={dueId} type="date" required aria-required="true" autoFocus min={indiaToday()} value={due} onChange={(e) => setDue(e.target.value)} />
          </div>
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save date"}</button>
            <button type="button" className="btn secondary small" onClick={() => close(ids.reschedule)}>Cancel</button>
          </div>
        </form>
      )}
      {mode === "cancel" && (
        <BdmAppointmentReasonForm label="Cancel task" submitText="Cancel it" busyText="Cancelling…" busy={busy}
          onSubmit={(reason) => void act("cancel", { reason }, "Cancelled.")} onCancel={() => close(ids.cancel)} />
      )}
      {mode === "view" && (p.can_complete || p.can_reschedule || p.can_edit || p.can_cancel) && (
        <div className="actions">
          {p.can_complete && <button type="button" className="btn small" disabled={busy} onClick={() => void act("complete", undefined, "Marked done.")}>{busy ? "Saving…" : "Done"}</button>}
          {p.can_reschedule && <button id={ids.reschedule} type="button" className="btn secondary small" disabled={busy} onClick={() => { setDue(task.due_on); setMode("reschedule"); }}>Reschedule</button>}
          {p.can_edit && <button id={ids.edit} type="button" className="btn secondary small" disabled={busy} onClick={() => setMode("edit")}>Edit</button>}
          {p.can_cancel && <button id={ids.cancel} type="button" className="btn secondary small" disabled={busy} onClick={() => setMode("cancel")}>Cancel task</button>}
        </div>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {sessionEnded && (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref="/overseas/login" />
        </div>
      )}
    </li>
  );
}

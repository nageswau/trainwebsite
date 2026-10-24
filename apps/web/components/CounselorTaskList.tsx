"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import CounselorTaskForm from "@/components/CounselorTaskForm";
import { sendJson } from "@/lib/apiErrors";
import {
  COUNSELOR_TASKS_API, groupByBand, LINK_TYPE_LABEL, linkHref, taskLine, type CounselorTask, type CounselorTaskOptions, type CounselorTaskStatus,
} from "@/lib/counselorTasks";
import { priorityClass, PRIORITY_LABEL } from "@/lib/managementTasks";

// ccrm-029 (T2/T3/T6): tasks in their bands. Each open task can be marked done or cancelled, a done one reopened; cancelling asks once
// more because it is final. Edit is offered where the API says so (`can_edit`). The admin's list also names each task's counselor.
export default function CounselorTaskList({ items, options, today, admin = false, empty }: {
  items: CounselorTask[]; options: CounselorTaskOptions; today: string; admin?: boolean; empty: string;
}) {
  const groups = groupByBand(items);
  if (groups.length === 0) return <p className="empty" role="status">{empty}</p>;
  return (
    <div style={{ display: "grid", gap: 18 }}>
      {groups.map((group) => (
        <section key={group.band} aria-labelledby={`band-${group.band}`}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span aria-hidden="true">{group.marker}</span>
            <h3 id={`band-${group.band}`} style={{ margin: 0 }}>{group.label} ({group.items.length})</h3>
          </div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 10 }}>
            {group.items.map((task) => (
              <li key={task.id} className="action-card" style={{ display: "grid", gap: 8, overflowWrap: "anywhere" }}>
                <TaskRow task={task} options={options} today={today} admin={admin} />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function TaskRow({ task, options, today, admin }: { task: CounselorTask; options: CounselorTaskOptions; today: string; admin: boolean }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function move(status: CounselorTaskStatus) {
    setBusy(true);
    setError("");
    const outcome = await sendJson(`${COUNSELOR_TASKS_API}/${task.id}`, "PATCH", { status });
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    setConfirmCancel(false);
    router.refresh(); // the task now belongs to another band
  }

  if (editing) return <CounselorTaskForm options={options} today={today} admin={admin} task={task} onClose={() => setEditing(false)} />;
  const givenBy = task.created_by.id !== task.counselor.id ? task.created_by.full_name : null;
  return (
    <>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
        <p style={{ margin: 0, fontWeight: 700 }}>{taskLine(task)}</p>
        <span className={priorityClass(task.priority)}>{PRIORITY_LABEL[task.priority]} priority</span>
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 14 }}>
        {admin && <>Counselor: {task.counselor.full_name}. </>}
        {task.link && (
          <>
            {LINK_TYPE_LABEL[task.link.type]}: {admin ? task.link.label : <Link href={linkHref(task.link)}>{task.link.label}</Link>}.{" "}
          </>
        )}
        {givenBy && <>Given by {givenBy}.</>}
      </p>
      {task.status !== "cancelled" && (
        <div className="actions">
          {task.status === "open" && <button className="btn" type="button" disabled={busy} onClick={() => void move("done")}>Mark done</button>}
          {task.status === "done" && <button className="btn secondary" type="button" disabled={busy} onClick={() => void move("open")}>Reopen</button>}
          {task.can_edit && <button className="btn secondary" type="button" disabled={busy} onClick={() => setEditing(true)}>Edit</button>}
          {!confirmCancel && <button className="btn ghost" type="button" disabled={busy} onClick={() => setConfirmCancel(true)}>Cancel task</button>}
        </div>
      )}
      {confirmCancel && (
        <div className="actions" role="group" aria-label={`Cancel “${task.title}”?`}>
          <span>Cancel this task? It can&apos;t be reopened.</span>
          <button className="btn" type="button" disabled={busy} onClick={() => void move("cancelled")}>Yes, cancel it</button>
          <button className="btn ghost" type="button" disabled={busy} onClick={() => setConfirmCancel(false)}>Keep it</button>
        </div>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
    </>
  );
}

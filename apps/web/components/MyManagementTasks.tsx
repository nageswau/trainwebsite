"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import ManagementTaskBands from "@/components/ManagementTaskBands";
import { sendJson } from "@/lib/apiErrors";
import { MY_STATUSES, STATUS_LABEL, type DiscussionStatus } from "@/lib/managementDiscussions";
import { MY_TASKS_API, taskLine, type MyTask, type MyTaskPage } from "@/lib/managementTasks";

// mgmt-028 (MT9): the tasks management assigned to a staff member, in the §28 bands. Only their own tasks reach this page (the API
// filters by owner); they move each one between Open, In Progress and Completed.
export default function MyManagementTasks({ data }: { data: MyTaskPage }) {
  return <ManagementTaskBands items={data.items} empty="No management tasks are assigned to you." renderItem={(task) => <TaskRow task={task} />} />;
}

function TaskRow({ task }: { task: MyTask }) {
  const router = useRouter();
  const [status, setStatus] = useState<DiscussionStatus>(task.status);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ text: string; failed: boolean } | null>(null);
  const id = `task-${task.id}-status`;

  async function update() {
    setBusy(true);
    setResult(null);
    const outcome = await sendJson(`${MY_TASKS_API}/${task.id}`, "PATCH", { status });
    setBusy(false);
    setResult(outcome.ok ? { text: "Status updated.", failed: false } : { text: outcome.message, failed: true });
    if (outcome.ok) router.refresh(); // the task may now belong to another band
  }

  return (
    <>
      <p style={{ margin: 0, fontWeight: 700 }}>{taskLine(task)}</p>
      <div className="form-grid" style={{ alignItems: "end" }}>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={id}>Status of “{task.title}”</label>
          <select id={id} value={status} disabled={busy} onChange={(e) => setStatus(e.target.value as DiscussionStatus)}>
            {MY_STATUSES.map((value) => <option key={value} value={value}>{STATUS_LABEL[value]}</option>)}
          </select>
        </div>
        <div className="actions">
          <button className="btn" type="button" disabled={busy || status === task.status} onClick={() => void update()}>{busy ? "Saving…" : "Update status"}</button>
        </div>
      </div>
      {result && <p className={result.failed ? "form-error" : "form-message"} role={result.failed ? "alert" : "status"}>{result.text}</p>}
    </>
  );
}

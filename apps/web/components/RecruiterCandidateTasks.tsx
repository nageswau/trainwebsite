"use client";
import Link from "next/link";
import { useEffect, useId, useState } from "react";

import RecruiterCandidateTaskForm from "@/components/RecruiterCandidateTaskForm";
import RecruiterCandidateTaskItem from "@/components/RecruiterCandidateTaskItem";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { candidateTasksUrl, TASKS_PATH, type CandidateTask } from "@/lib/recruiterCandidateTasks";
import { getPage } from "@/lib/telecallerCatalogue";

/** hrc-016 (T11): a candidate's tasks -- open ones by due time, then done / cancelled. Readers see them; writers add, edit, complete and
 *  cancel (`canAdd` + each task's `can_change`). Every write re-reads the list and calls `onChanged` (the page re-reads the timeline). */
export default function RecruiterCandidateTasks({ candidateId, canAdd, onChanged }: { candidateId: string; canAdd: boolean; onChanged?: () => void }) {
  const id = useId();
  const [tasks, setTasks] = useState<CandidateTask[] | null>(null);
  const [total, setTotal] = useState(0);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const reload = () => setVersion((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<CandidateTask>(candidateTasksUrl(candidateId), controller.signal)
      .then((page) => { setTasks(page.items); setTotal(page.total); })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [candidateId, version]);

  const changed = (text: string, failedWrite = false) => { setNotice({ text, failed: failedWrite }); reload(); onChanged?.(); };
  const headingId = `${id}-heading`;
  return (
    <section className="action-card" aria-labelledby={headingId} aria-busy={tasks === null && !failed}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", justifyContent: "space-between" }}>
        <h3 id={headingId} style={{ margin: 0 }}>Tasks</h3>
        {canAdd && <Link href={TASKS_PATH} style={LINK_STYLE}>My tasks</Link>}
      </div>
      <div role="status" aria-live="polite">
        {notice && <p className={notice.failed ? "form-error" : "form-message"} style={{ margin: "8px 0 0" }}>{notice.text}</p>}
      </div>
      {canAdd && !adding && (
        <div className="actions" style={{ marginTop: 8 }}>
          <button type="button" className="btn small" onClick={() => { setNotice(null); setAdding(true); }}>Add task</button>
        </div>
      )}
      {adding && (
        <RecruiterCandidateTaskForm candidateId={candidateId} onCancel={() => setAdding(false)}
          onSaved={() => { setAdding(false); changed("Task added."); }} />
      )}
      {failed ? (
        <div style={{ marginTop: 8 }}>
          <p className="form-error" role="alert">Unable to load tasks.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : tasks === null ? (
        <p className="muted" role="status">Loading tasks…</p>
      ) : tasks.length === 0 ? (
        <p className="muted" style={{ margin: "8px 0 0" }}>No tasks yet.</p>
      ) : (
        <>
          <ul aria-label="Candidate tasks" style={{ padding: 0, margin: "8px 0 0", display: "grid", gap: 8 }}>
            {tasks.map((task) => (
              <RecruiterCandidateTaskItem key={task.id} task={task} onChanged={(_, text) => changed(text)} onRefused={(text) => changed(text, true)} />
            ))}
          </ul>
          {total > tasks.length && <p className="muted" style={{ fontSize: 13 }}>Showing the first {tasks.length} of {total} tasks.</p>}
        </>
      )}
    </section>
  );
}

"use client";
import { useEffect, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { completeUrl, kindLabel, type RequirementTask, tasksUrl } from "@/lib/recruiterAutomation";

const STATUS_LABEL: Record<RequirementTask["status"], string> = { open: "Open", done: "Done", cancelled: "Cancelled" };

/** pob-027 (DEC-SCOPE-434 I5/I6): the tasks a requirement's owner started with. `version` re-reads them when the requirement changes (an
 * assignment moves the open ones). The server decides who may complete one (`can_complete`). */
export default function RequirementTasks({ requirementId, version }: { requirementId: string; version: string }) {
  const [tasks, setTasks] = useState<RequirementTask[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const inFlight = useRef(false);
  const id = `requirement-${requirementId}-tasks`;

  useEffect(() => {
    let live = true;
    void sendRequest(tasksUrl(requirementId), {}).then((outcome) => {
      if (!live) return;
      if (outcome.ok) {
        setTasks((outcome.data as { items: RequirementTask[] }).items);
        setLoadError(null);
      } else setLoadError(outcome.message);
    });
    return () => {
      live = false;
    };
  }, [requirementId, version]);

  async function complete(task: RequirementTask) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusyId(task.id);
    setFailure(null);
    const outcome = await sendJson(completeUrl(requirementId, task.id), "POST", {});
    inFlight.current = false;
    setBusyId(null);
    if (!outcome.ok) return setFailure(outcome.message);
    const saved = (outcome.data as { task: RequirementTask }).task;
    setTasks((current) => (current ?? []).map((t) => (t.id === saved.id ? saved : t)));
  }

  return (
    <section className="action-card wide" aria-labelledby={id}>
      <h3 id={id} style={{ marginTop: 0 }}>Tasks</h3>
      {loadError && <p className="form-error" role="alert">{loadError}</p>}
      {!tasks && !loadError && <p className="muted" role="status">Loading tasks…</p>}
      {tasks && tasks.length === 0 && <p className="muted">No tasks on this requirement.</p>}
      {tasks && tasks.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
          {tasks.map((task) => (
            <li key={task.id} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
              <div>
                <strong>{task.title}</strong>
                <div className="muted" style={{ fontSize: 13 }}>
                  {kindLabel(task.kind)} · {task.assignee?.full_name ?? "Unassigned"} · due <LocalTime value={task.due_at} time />
                  {task.completed_at && <> · done <LocalTime value={task.completed_at} time /></>}
                </div>
              </div>
              {task.can_complete ? (
                <button type="button" className="btn small secondary" disabled={busyId !== null} aria-label={`Mark done: ${task.title}`} onClick={() => complete(task)}>
                  {busyId === task.id ? "Saving…" : "Mark done"}
                </button>
              ) : (
                <span className="muted">{STATUS_LABEL[task.status]}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
    </section>
  );
}

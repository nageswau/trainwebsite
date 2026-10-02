"use client";

import { useState } from "react";

import AgentTaskForm from "./AgentTaskForm";
import AgentTasksPanel from "./AgentTasksPanel";
import type { TaskView } from "@/lib/agentTasks";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// AGN-016 (DEC-SCOPE-051): "New task" + the list, shared by the Tasks page (student picked in the form) and a student's card (student
// fixed; read-only when archived). After a save the list reloads and focus returns to the New task button.
export default function AgentTasksBlock({ view, studentId, archived = false, Heading = "h3" }: { view: TaskView; studentId?: string; archived?: boolean; Heading?: "h3" | "h6" }) {
  const [adding, setAdding] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [notice, setNotice] = useState("");
  const focusLater = useFocusAfterRender();
  const addId = `task-new-${studentId ?? "page"}`;

  function finish(message?: string) {
    setAdding(false);
    if (message) {
      setNotice(message);
      setReloadKey((k) => k + 1);
    }
    focusLater(addId);
  }

  return (
    <div>
      {archived && <p className="muted">This student is archived; their tasks are read-only.</p>}
      <p aria-live="polite" className={notice ? "form-message" : undefined} style={notice ? undefined : { margin: 0 }}>{notice}</p>
      {!archived &&
        (adding ? (
          <div className="card" style={{ padding: 16 }} role="group" aria-labelledby={`${addId}-heading`}>
            {/* QA16-05: a visible title for the open form, one level below the page's or the student card's heading. */}
            <Heading id={`${addId}-heading`} style={{ fontSize: 17, margin: 0 }}>New task</Heading>
            <AgentTaskForm mode="create" studentId={studentId} onCancel={() => finish()} onSaved={(t) => finish(`“${t.title}” added.`)} onGone={() => finish("This student is no longer available to you.")} />
          </div>
        ) : (
          <button id={addId} type="button" className="btn small" onClick={() => setAdding(true)}>New task</button>
        ))}
      <AgentTasksPanel view={view} studentId={studentId} readOnly={archived} reloadKey={reloadKey} Heading={Heading} />
    </div>
  );
}

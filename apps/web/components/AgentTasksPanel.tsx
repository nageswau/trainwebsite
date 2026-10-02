"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import AgentTaskCard, { cancelId, doneId, editId } from "./AgentTaskCard";
import AgentTaskForm from "./AgentTaskForm";
import { isPage, NOT_COMPLETED, type Page, sendJson } from "@/lib/apiErrors";
import { failureText } from "@/lib/agentShortlist";
import { type AgentTask, EMPTY_TEXT, PAGE_SIZE, TASKS_URL, type TaskView, taskUrl } from "@/lib/agentTasks";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// AGN-016 (DEC-SCOPE-051): a page of tasks -- the Tasks page (a view) or one student's card (`studentId`, view "all"). Masters and
// the student's assigned staff complete, edit and cancel open tasks; the server refuses everything else (409/404), and the list
// reloads so the screen shows what is true. Loading, paging, Retry and the inline confirm follow AgentShortlistPanel.
export default function AgentTasksPanel({ view, studentId, readOnly = false, reloadKey = 0, Heading = "h3" }: {
  view: TaskView;
  studentId?: string;
  readOnly?: boolean;
  reloadKey?: number;
  Heading?: "h3" | "h6";
}) {
  const [data, setData] = useState<Page<AgentTask> | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [offset, setOffset] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const focusLater = useFocusAfterRender();
  const listId = `tasks-list-${studentId ?? view}`;
  const resultsId = `tasks-results-${studentId ?? view}`; // focus fallback when the list itself is gone (its last task closed)

  const load = useCallback(() => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setLoadError(null);
    const params = new URLSearchParams({ view, limit: String(PAGE_SIZE), offset: String(offset) });
    if (studentId) params.set("student", studentId);
    fetch(`${TASKS_URL}?${params}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (controller.signal.aborted) return;
        if (!response.ok || !isPage<AgentTask>(body)) return setLoadError(failureText(response.status, body?.detail, "Unable to load tasks."));
        if (body.items.length === 0 && body.offset > 0) return setOffset(Math.max(0, body.offset - PAGE_SIZE));
        setData(body);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadError("Unable to load tasks.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [view, studentId, offset]);

  useEffect(load, [load, reloadKey]);
  useEffect(() => () => request.current?.abort(), []);

  async function close(t: AgentTask, status: "done" | "cancelled") {
    if (busyId) return;
    setBusyId(t.id);
    setActionError(null);
    const outcome = await sendJson(taskUrl(t.id), "PATCH", { status });
    setBusyId(null);
    setConfirmId(null);
    if (outcome.ok) {
      setNotice(status === "done" ? `“${t.title}” marked done.` : `“${t.title}” cancelled.`);
    } else if (outcome.status === 404 || outcome.status === 409) {
      // Someone else closed it, the student was archived or reassigned: say so, then show what is true now.
      setNotice(outcome.status === 404 ? "This task is no longer available to you." : outcome.message);
    } else {
      setActionError(outcome.status ? failureText(outcome.status, outcome.message, "Unable to update the task.") : NOT_COMPLETED);
      return focusLater(doneId(t.id));
    }
    load();
    focusLater(listId, resultsId);
  }

  function stopEditing(t: AgentTask, message?: string) {
    setEditingId(null);
    if (message) {
      setNotice(message);
      load();
    }
    focusLater(editId(t.id), listId, resultsId);
  }

  return (
    <div>
      <p aria-live="polite" className={notice ? "form-message" : undefined} style={notice ? undefined : { margin: 0 }}>{notice}</p>
      {actionError && <p className="form-error" role="alert">{actionError}</p>}
      <div id={resultsId} role="region" aria-label="Task results" tabIndex={-1} aria-busy={loading} style={{ marginTop: 12, opacity: loading && data ? 0.6 : 1 }}>
        {loadError ? (
          <>
            <p className="form-error" role="alert">{loadError}</p>
            <button type="button" className="btn secondary small" aria-label="Retry loading tasks" onClick={load}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted">Loading tasks…</p>
        ) : data.items.length === 0 ? (
          <p className="muted">{EMPTY_TEXT[view]}</p>
        ) : (
          <>
            <ul id={listId} tabIndex={-1} aria-label="Tasks" className="grid two" style={{ listStyle: "none", padding: 0, margin: 0, gap: 12 }}>
              {data.items.map((t) =>
                editingId === t.id ? (
                  <li key={t.id} className="card" style={{ padding: 16 }} aria-label={`Editing “${t.title}”`}>
                    <AgentTaskForm mode="edit" task={t} onCancel={() => stopEditing(t)} onSaved={(saved) => stopEditing(t, `“${saved.title}” saved.`)} onGone={() => stopEditing(t, "This task is no longer available to you.")} />
                  </li>
                ) : (
                  <AgentTaskCard
                    key={t.id}
                    t={t}
                    Heading={Heading}
                    actionable={!readOnly && t.student.status === "active" && editingId === null}
                    busy={busyId === t.id}
                    confirming={confirmId === t.id}
                    onDone={() => void close(t, "done")}
                    onEdit={() => {
                      setConfirmId(null);
                      setEditingId(t.id);
                    }}
                    onAskCancel={() => setConfirmId(t.id)}
                    onKeep={() => {
                      setConfirmId(null);
                      focusLater(cancelId(t.id));
                    }}
                    onCancel={() => void close(t, "cancelled")}
                  />
                ),
              )}
            </ul>
            <p className="muted" style={{ marginTop: 8 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</p>
            {data.total > PAGE_SIZE && (
              <nav aria-label="Task pages" className="actions" style={{ gap: 8 }}>
                <button type="button" className="btn secondary small" aria-label="Previous page of tasks" disabled={data.offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
                <button type="button" className="btn secondary small" aria-label="Next page of tasks" disabled={data.offset + data.items.length >= data.total || loading} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
              </nav>
            )}
          </>
        )}
      </div>
    </div>
  );
}

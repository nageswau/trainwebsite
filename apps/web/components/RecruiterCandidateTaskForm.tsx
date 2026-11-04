"use client";
import { type ChangeEvent, type FormEvent, useEffect, useId, useState } from "react";

import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson, type SendOutcome } from "@/lib/apiErrors";
import { istInputToIso, isoToIstInput, nowIstInput } from "@/lib/bdmAppointments";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import type { PickOption } from "@/lib/lookups";
import { RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import {
  candidateApplicationsUrl, isCandidateTask, NOTE_MAX, newTaskUrl, TASK_TYPES, taskAssigneeSearch, taskUrl, TITLE_MAX, type CandidateTask,
} from "@/lib/recruiterCandidateTasks";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

type Values = { task_type: string; title: string; due: string; application_id: string; notes: string };
type ApplicationOption = { id: string; label: string };

/** hrc-016 (T3/T6): add a task to a candidate, or edit an open one (type, title, due, assignee, notes; the application link is fixed once
 *  set). Times are entered in IST. The API decides every rule; its answers land on the fields, and typed text is never cleared. */
export default function RecruiterCandidateTaskForm({ candidateId, task, onSaved, onCancel }: {
  candidateId: string; task?: CandidateTask; onSaved: (task: CandidateTask) => void; onCancel: () => void;
}) {
  const id = useId();
  const [start] = useState<Values>({
    task_type: task?.task_type ?? "", title: task?.title ?? "", due: task ? isoToIstInput(task.due_at) : "", application_id: task?.application_id ?? "",
    notes: task?.notes ?? "",
  });
  const startAssignee: PickOption | null = task ? { id: task.assignee.id, label: task.assignee.full_name } : null;
  const [v, setV] = useState(start);
  const [assignee, setAssignee] = useState<PickOption | null>(startAssignee);
  const [applications, setApplications] = useState<ApplicationOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [now] = useState(nowIstInput);
  const dirty = (Object.keys(start) as (keyof Values)[]).some((key) => v[key] !== start[key]) || assignee?.id !== startAssignee?.id;
  useLeaveGuard(!busy && dirty, "Discard this task?");

  useEffect(() => { // the candidate's applications, for the optional link (create only)
    if (task) return;
    const controller = new AbortController();
    fetch(candidateApplicationsUrl(candidateId), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : { items: [] }))
      .then((body: { items?: { id: string; requirement: { code: string | null; title: string }; company: { name: string } }[] }) =>
        setApplications((body.items ?? []).map((a) => ({ id: a.id, label: `${a.requirement.code ?? ""} ${a.requirement.title} — ${a.company.name}`.trim() }))))
      .catch(() => undefined); // the link is optional: without the list the form still works
    return () => controller.abort();
  }, [candidateId, task]);

  const fid = (key: string) => `${id}-${key}`;
  const set = (key: keyof Values) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setV({ ...v, [key]: e.target.value });
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;

  function send(): Promise<SendOutcome> | null {
    const body = { task_type: v.task_type, title: v.title.trim(), due_at: istInputToIso(v.due), assignee_user_id: assignee?.id, notes: v.notes.trim() || null };
    if (!task) return sendJson(newTaskUrl(candidateId), "POST", { ...body, application_id: v.application_id || null });
    const changes: Record<string, unknown> = {};
    if (v.task_type !== start.task_type) changes.task_type = body.task_type;
    if (body.title !== task.title) changes.title = body.title;
    if (v.due !== start.due) changes.due_at = body.due_at;
    if (assignee?.id !== task.assignee.id) changes.assignee_user_id = body.assignee_user_id;
    if (body.notes !== (task.notes ?? null)) changes.notes = body.notes;
    return Object.keys(changes).length ? sendJson(taskUrl(task.id), "PATCH", changes) : null;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const missing: Record<string, string> = {};
    if (!v.task_type) missing.task_type = "Choose a task type";
    if (!v.title.trim()) missing.title = "Enter a title";
    if (!v.due) missing.due_at = "Choose a due date and time";
    if (!assignee) missing.assignee_user_id = "Choose who does it";
    if (Object.keys(missing).length) return setErrors(missing);
    const request = send();
    if (!request) return onCancel();
    setBusy(true);
    setErrors({});
    setFailure(null);
    setSessionEnded(false);
    const result = await request;
    setBusy(false);
    if (result.ok) return isCandidateTask(result.data) ? onSaved(result.data) : setFailure(SAVE_FAILED);
    const placed = fieldErrors(result.detail);
    if (Object.keys(placed).length) return setErrors(placed);
    const kind = writeFailure(result.status);
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message); // a refusal (inactive assignee, archived candidate) in the server's words
  }

  return (
    <form aria-label={task ? "Edit task" : "Add task"} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="form-grid" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
        <div className="field">
          <label htmlFor={fid("task_type")}>Type (required)</label>
          <select id={fid("task_type")} autoFocus required aria-required="true" value={v.task_type} onChange={set("task_type")} {...invalid("task_type")}>
            <option value="">Select a type</option>
            {TASK_TYPES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
          {error("task_type")}
        </div>
        <div className="field">
          <label htmlFor={fid("title")}>Title (required)</label>
          <input id={fid("title")} required aria-required="true" maxLength={TITLE_MAX} value={v.title} onChange={set("title")} {...invalid("title")} />
          {error("title")}
        </div>
        <div className="field">
          <label htmlFor={fid("due_at")}>Due date and time (IST, required)</label>
          <input id={fid("due_at")} type="datetime-local" required aria-required="true" min={now} value={v.due} onChange={set("due")} {...invalid("due_at")} />
          {error("due_at")}
        </div>
        <div className="field">
          <SearchableSelect id={fid("assignee")} label="Assigned to (required)" noun="employee" required search={taskAssigneeSearch} initial={startAssignee}
            disabled={busy} onChange={setAssignee} />
          {error("assignee_user_id")}
        </div>
        {!task && (
          <div className="field">
            <label htmlFor={fid("application_id")}>About an application</label>
            <select id={fid("application_id")} value={v.application_id} onChange={set("application_id")} {...invalid("application_id")}>
              <option value="">No specific application</option>
              {applications.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
            </select>
            {error("application_id")}
          </div>
        )}
      </div>
      <div className="field">
        <label htmlFor={fid("notes")}>Notes</label>
        <textarea id={fid("notes")} rows={3} maxLength={NOTE_MAX} value={v.notes} onChange={set("notes")} aria-invalid={errors.notes ? true : undefined}
          aria-describedby={errors.notes ? `${fid("notes")}-count ${fid("notes")}-error` : `${fid("notes")}-count`} />
        <p id={`${fid("notes")}-count`} className="muted" style={{ margin: 0 }}>{v.notes.length}/{NOTE_MAX}</p>
        {error("notes")}
      </div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {sessionEnded && (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref={RECRUITER_SIGN_IN} />
        </div>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : task ? "Save changes" : "Add task"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

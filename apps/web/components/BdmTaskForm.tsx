"use client";
import { type ChangeEvent, type FormEvent, useId, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { myOrganizationSearch, todayIst } from "@/lib/bdmAppointments";
import { isTask, KIND_LABEL, KINDS, NOTES_MAX, type Task, type TaskKind, TASKS_URL, taskRuleField, taskUrl, TITLE_MAX } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import type { PickOption } from "@/lib/lookups";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

// bdm-008 (spec §9): add a follow-up or task, or change an open one of your own. The API decides every rule (dates, organization,
// lengths); this form only helps. Typed text is never cleared by a failed save; leaving with unsaved text asks first.
export default function BdmTaskForm({ task, organization, onSaved, onCancel }: {
  task?: Task; organization?: { id: string; name: string }; onSaved: (task: Task) => void; onCancel: () => void;
}) {
  const id = useId();
  const [start] = useState({ kind: (task?.kind ?? "follow_up") as TaskKind, title: task?.title ?? "", due_on: task?.due_on ?? "", notes: task?.notes ?? "" });
  const [v, setV] = useState(start);
  const [org, setOrg] = useState<PickOption | null>(null);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [today] = useState(todayIst);
  useLeaveGuard(!busy && (v.title !== start.title || v.notes !== start.notes || v.due_on !== start.due_on), "Discard this task?");
  const fid = (key: string) => `${id}-${key}`;
  const set = (key: keyof typeof v) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setV({ ...v, [key]: e.target.value });
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const missing: Record<string, string> = {};
    if (!v.title.trim()) missing.title = "Title is required";
    if (!v.due_on) missing.due_on = "Choose a due date";
    if (Object.keys(missing).length) return setErrors(missing);
    setBusy(true);
    setErrors({});
    setFailure(null);
    const common = { title: v.title, due_on: v.due_on, notes: v.notes.trim() || null };
    const orgId = organization?.id ?? org?.id;
    const result = task
      ? await sendJson(taskUrl(task.id), "PATCH", common)
      : await sendJson(TASKS_URL, "POST", { kind: v.kind, ...common, ...(orgId ? { organization_id: orgId } : {}) });
    setBusy(false);
    if (result.ok && isTask(result.data)) return onSaved(result.data);
    if (result.ok) return setFailure("The task couldn't be saved. Try again.");
    const placed = { ...fieldErrors(result.detail), ...taskRuleField(result.detail) };
    if (Object.keys(placed).length) return setErrors(placed);
    setFailure(result.message);
  }

  return (
    <form aria-label={task ? "Edit task" : "Add follow-up or task"} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      {!task && (
        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend>Kind</legend>
          {KINDS.map((k) => (
            <label key={k} style={{ marginRight: 16 }}>
              <input type="radio" name={fid("kind")} value={k} checked={v.kind === k} onChange={() => setV({ ...v, kind: k })} /> {KIND_LABEL[k]}
            </label>
          ))}
        </fieldset>
      )}
      <div className="field">
        <label htmlFor={fid("title")}>Title (required)</label>
        <input id={fid("title")} autoFocus required aria-required="true" maxLength={TITLE_MAX} value={v.title} onChange={set("title")} {...invalid("title")} />
        {error("title")}
      </div>
      <div className="field">
        <label htmlFor={fid("due_on")}>Due date (IST, required)</label>
        <input id={fid("due_on")} type="date" required aria-required="true" min={task && start.due_on < today ? undefined : today} value={v.due_on} onChange={set("due_on")} {...invalid("due_on")} />
        {error("due_on")}
      </div>
      {!task && (organization ? (
        <p className="field" style={{ margin: 0 }}><span className="muted">Organization: </span>{organization.name}</p>
      ) : (
        <div className="field">
          <SearchableSelect label="Organization (optional)" noun="organization" search={myOrganizationSearch()} initial={null} onChange={setOrg} />
          {error("organization_id")}
        </div>
      ))}
      <div className="field">
        <label htmlFor={fid("notes")}>Notes</label>
        <textarea id={fid("notes")} rows={3} maxLength={NOTES_MAX} value={v.notes} onChange={set("notes")} aria-invalid={errors.notes ? true : undefined}
          aria-describedby={errors.notes ? `${fid("notes")}-count ${fid("notes")}-error` : `${fid("notes")}-count`} />
        <p id={`${fid("notes")}-count`} className="muted" style={{ margin: 0 }}>{v.notes.length}/{NOTES_MAX}</p>
        {error("notes")}
      </div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : task ? "Save changes" : "Add"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

"use client";
import { type ChangeEvent, type FormEvent, useEffect, useId, useState } from "react";

import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import type { PickOption } from "@/lib/lookups";
import { KIND_LABEL, KINDS, NOTES_MAX, type PartnershipTask, PRIORITIES, PRIORITY_LABEL, type TaskKind, TASKS_URL, taskOf, taskUrl, TITLE_MAX } from "@/lib/partnershipTasks";
import { indiaToday, leadOptions, universityOptions } from "@/lib/visits";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

// The API answers its date, scope and assignee rules as one sentence; put each on the field it is about.
function ruleField(detail: unknown): Record<string, string> {
  if (typeof detail !== "string") return {};
  if (detail.startsWith("The due date")) return { due_on: detail };
  if (detail.startsWith("Choose yourself")) return { assignee_user_id: detail };
  if (detail.startsWith("Choose a university") || detail.startsWith("Only the university")) return { university_id: detail };
  return {};
}

// upc-020: add a follow-up or task (TK9/TK10), or edit an open one's title, priority, notes and -- for a head -- assignee (TK12; the
// due date moves through Reschedule). The university and assignee pickers reuse upc-010's option searches, which already return only
// what the caller may submit. Typed text is never cleared by a failed save; leaving with unsaved text asks first.
export default function PartnershipTaskForm({ task, university, canAssign, onSaved, onCancel }: {
  task?: PartnershipTask; university?: { id: string; name: string }; canAssign: boolean; onSaved: (task: PartnershipTask) => void; onCancel: () => void;
}) {
  const id = useId();
  const [start] = useState({ kind: (task?.kind ?? "follow_up") as TaskKind, title: task?.title ?? "", due_on: "", priority: task?.priority ?? "medium", notes: task?.notes ?? "" });
  const [v, setV] = useState(start);
  const [pickedUniversity, setPickedUniversity] = useState<PickOption | null>(null);
  const [assignee, setAssignee] = useState<PickOption | null>(null);
  const [titles, setTitles] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  useLeaveGuard(!busy && (v.title !== start.title || v.notes !== start.notes), "Discard this task?");
  const fid = (key: string) => `${id}-${key}`;
  const set = (key: keyof typeof v) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setV({ ...v, [key]: e.target.value });
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;

  useEffect(() => {
    // TK3: the §19 titles are suggestions only; without them the title is still free text.
    let live = true;
    fetch(`${TASKS_URL}/catalogue`)
      .then((r) => (r.ok ? r.json() : null))
      .then((body: { titles?: unknown } | null) => live && Array.isArray(body?.titles) && setTitles(body.titles.filter((t): t is string => typeof t === "string")))
      .catch(() => undefined);
    return () => { live = false; };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const universityId = university?.id ?? pickedUniversity?.id;
    const missing: Record<string, string> = {};
    if (!v.title.trim()) missing.title = "Title is required";
    if (!task && !v.due_on) missing.due_on = "Choose a due date";
    if (!task && !universityId) missing.university_id = "Choose a university";
    if (Object.keys(missing).length) return setErrors(missing);
    setBusy(true);
    setErrors({});
    setFailure(null);
    setSessionEnded(false);
    const common = { title: v.title, priority: v.priority, notes: v.notes.trim() || null };
    const assigned = assignee && assignee.id !== task?.assignee.id ? { assignee_user_id: assignee.id } : {};
    const result = task
      ? await sendJson(taskUrl(task.id), "PATCH", { ...common, ...assigned })
      : await sendJson(TASKS_URL, "POST", { university_id: universityId, kind: v.kind, title: v.title, due_on: v.due_on, priority: v.priority, notes: common.notes, ...assigned });
    setBusy(false);
    const saved = result.ok ? taskOf(result.data) : null;
    if (saved) return onSaved(saved);
    if (result.ok) return setFailure(SAVE_FAILED);
    const placed = { ...fieldErrors(result.detail), ...ruleField(result.detail) };
    if (Object.keys(placed).length) return setErrors(placed);
    const kind = writeFailure(result.status); // never the server's raw 5xx text; the typed text stays either way
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message);
  }

  return (
    <form aria-label={task ? "Edit task" : "Add follow-up or task"} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      {!task && (university ? (
        <p className="field" style={{ margin: 0 }}><span className="muted">University: </span>{university.name}</p>
      ) : (
        <div className="field">
          <SearchableSelect label="University (required)" noun="university" required search={universityOptions} initial={null} onChange={setPickedUniversity} />
          {error("university_id")}
        </div>
      ))}
      {!task && (
        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend>Kind</legend>
          {KINDS.map((k) => (
            <label key={k} style={{ marginRight: 16, display: "inline-flex", gap: 6, alignItems: "center", minHeight: 32 }}>
              <input type="radio" name={fid("kind")} value={k} checked={v.kind === k} onChange={() => setV({ ...v, kind: k })} /> {KIND_LABEL[k]}
            </label>
          ))}
        </fieldset>
      )}
      <div className="field">
        <label htmlFor={fid("title")}>Title (required)</label>
        <input id={fid("title")} autoFocus required aria-required="true" maxLength={TITLE_MAX} list={fid("titles")} value={v.title} onChange={set("title")} {...invalid("title")} />
        <datalist id={fid("titles")}>{titles.map((t) => <option key={t} value={t} />)}</datalist>
        {error("title")}
      </div>
      {!task && (
        <div className="field">
          <label htmlFor={fid("due_on")}>Due date (IST, required)</label>
          <input id={fid("due_on")} type="date" required aria-required="true" min={indiaToday()} value={v.due_on} onChange={set("due_on")} {...invalid("due_on")} />
          {error("due_on")}
        </div>
      )}
      <div className="field">
        <label htmlFor={fid("priority")}>Priority</label>
        <select id={fid("priority")} value={v.priority} onChange={set("priority")}>
          {PRIORITIES.map((p) => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
        </select>
      </div>
      {canAssign && (
        <div className="field">
          <SearchableSelect label="Assign to" noun="manager" search={leadOptions}
            initial={task ? { id: task.assignee.id, label: task.assignee.full_name } : null} onChange={setAssignee} />
          <p className="muted" style={{ margin: 0 }}>Yourself or an active manager in your team. Leave empty to assign it to yourself.</p>
          {error("assignee_user_id")}
        </div>
      )}
      <div className="field">
        <label htmlFor={fid("notes")}>Notes</label>
        <textarea id={fid("notes")} rows={3} maxLength={NOTES_MAX} value={v.notes} onChange={set("notes")} aria-invalid={errors.notes ? true : undefined}
          aria-describedby={errors.notes ? `${fid("notes")}-count ${fid("notes")}-error` : `${fid("notes")}-count`} />
        <p id={`${fid("notes")}-count`} className="muted" style={{ margin: 0 }}>{v.notes.length}/{NOTES_MAX}</p>
        {error("notes")}
      </div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {sessionEnded && (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref="/overseas/login" />
        </div>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : task ? "Save changes" : "Add"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

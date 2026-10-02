"use client";

import { FormEvent, useEffect, useId, useRef, useState } from "react";

import SearchableSelect from "./SearchableSelect";
import { isPage, NOT_COMPLETED, sendJson } from "@/lib/apiErrors";
import { APPLICATIONS_URL, type AgentApplicationItem } from "@/lib/agentApplications";
import { failureText } from "@/lib/agentShortlist";
import { searchStudents } from "@/lib/agentStudents";
import { type AgentTask, buildCreatePayload, buildUpdatePayload, type DraftField, draftFromTask, emptyDraft, isPastLocal, NOTES_MAX, TASKS_URL, taskUrl, TITLE_MAX, validateDraft } from "@/lib/agentTasks";

type Props =
  | { mode: "create"; studentId?: string; task?: undefined; onCancel: () => void; onSaved: (t: AgentTask) => void; onGone?: () => void }
  | { mode: "edit"; task: AgentTask; studentId?: undefined; onCancel: () => void; onSaved: (t: AgentTask) => void; onGone?: () => void };

// AGN-016 (DEC-SCOPE-051): create or edit a task. The student is picked (Tasks page) or fixed (student card, edit); its applications
// load once it is known. A 422 keeps the form and the entry; a 404 (the task or student left the caller's scope) is the host's to handle.
export default function AgentTaskForm({ mode, task, studentId, onCancel, onSaved, onGone }: Props) {
  const id = useId().replaceAll(":", "");
  const [draft, setDraft] = useState(() => (task ? draftFromTask(task) : emptyDraft(studentId ?? "")));
  const [errors, setErrors] = useState<Partial<Record<DraftField, string>>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [applications, setApplications] = useState<AgentApplicationItem[] | null>(null);
  const [appsFailed, setAppsFailed] = useState(false);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const fixedStudent = mode === "edit" || !!studentId;

  useEffect(() => {
    if (!draft.studentId) return setApplications(null);
    const controller = new AbortController();
    setApplications(null);
    setAppsFailed(false);
    // `all` lists every application except withdrawn ones -- the ones a task may link to (T4).
    fetch(`${APPLICATIONS_URL}?student=${draft.studentId}&status=all&limit=100`, { signal: controller.signal })
      .then((r) => r.json().then((body) => (r.ok && isPage<AgentApplicationItem>(body) ? setApplications(body.items) : setAppsFailed(true))))
      .catch(() => !controller.signal.aborted && setAppsFailed(true));
    return () => controller.abort();
  }, [draft.studentId]);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  const set = (field: keyof typeof draft) => (value: string) => setDraft((d) => ({ ...d, [field]: value, ...(field === "studentId" ? { applicationId: "" } : {}) }));
  const fieldId = (f: string) => `${id}-${f}`;
  const invalid = (f: DraftField) => (errors[f] ? { "aria-invalid": true as const, "aria-describedby": fieldId(`${f}-error`) } : {});
  const fieldError = (f: DraftField) => errors[f] && <span id={fieldId(`${f}-error`)} className="form-error" style={{ padding: "6px 10px" }}>{errors[f]}</span>;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const found = validateDraft(draft);
    setErrors(found);
    const first = (["studentId", "title", "dueLocal", "notes"] as const).find((f) => found[f]);
    if (first) return document.getElementById(fieldId(first))?.focus();
    const payload = task ? buildUpdatePayload(draft, task) : buildCreatePayload(draft);
    if (task && Object.keys(payload).length === 0) return onCancel(); // nothing changed: nothing to send or audit
    setBusy(true);
    setError(null);
    const outcome = await sendJson(task ? taskUrl(task.id) : TASKS_URL, task ? "PATCH" : "POST", payload);
    setBusy(false);
    if (outcome.ok) return onSaved(outcome.data.task as AgentTask);
    if (outcome.status === 404 && onGone) return onGone();
    setError(outcome.status ? failureText(outcome.status, outcome.message, "Unable to save the task.") : NOT_COMPLETED);
  }

  const past = isPastLocal(draft.dueLocal);
  return (
    <form className="form" noValidate onSubmit={submit} onKeyDown={(k) => {
        // An Escape the student picker already used (closing its open list) is not a cancel: the entry is kept.
        if (k.key === "Escape" && !k.defaultPrevented) {
          k.stopPropagation(); // the student detail panel closes on Escape too; only the form closes here
          onCancel();
        }
      }} aria-busy={busy} style={{ marginTop: 12 }}>
      {error && <p ref={errorRef} tabIndex={-1} className="form-error" role="alert">{error}</p>}
      {!fixedStudent && (
        <div className="field">
          <SearchableSelect id={fieldId("studentId")} label="Student" noun="student" required search={searchStudents} onChange={(o) => set("studentId")(o?.id ?? "")} />
          {fieldError("studentId")}
        </div>
      )}
      <div className="field">
        <label htmlFor={fieldId("title")}>Title</label>
        <input id={fieldId("title")} value={draft.title} maxLength={TITLE_MAX} required autoComplete="off" onChange={(e) => set("title")(e.target.value)} {...invalid("title")} />
        {fieldError("title")}
      </div>
      <div className="field">
        <label htmlFor={fieldId("dueLocal")}>Due</label>
        <input id={fieldId("dueLocal")} type="datetime-local" value={draft.dueLocal} required onChange={(e) => set("dueLocal")(e.target.value)} {...invalid("dueLocal")} />
        <span className="muted" aria-live="polite" style={{ fontSize: 13 }}>{past ? "This time has passed — the task will show as overdue." : ""}</span>
        {fieldError("dueLocal")}
      </div>
      <div className="field">
        <label htmlFor={fieldId("application")}>Application (optional)</label>
        <select id={fieldId("application")} value={draft.applicationId} disabled={!draft.studentId || applications === null} onChange={(e) => set("applicationId")(e.target.value)}>
          <option value="">{!draft.studentId ? "Choose a student first" : applications === null && !appsFailed ? "Loading applications…" : "None"}</option>
          {(applications ?? []).map((a) => (
            <option key={a.id} value={a.id}>{`${a.university} — ${a.intake}`}</option>
          ))}
        </select>
        {appsFailed && <span className="muted" style={{ fontSize: 13 }}>Applications couldn&apos;t be loaded; you can save without one.</span>}
      </div>
      <div className="field">
        <label htmlFor={fieldId("notes")}>Notes (optional)</label>
        <textarea id={fieldId("notes")} value={draft.notes} maxLength={NOTES_MAX} aria-describedby={fieldId("notes-count")} onChange={(e) => set("notes")(e.target.value)} {...invalid("notes")} />
        <span id={fieldId("notes-count")} className="muted" style={{ fontSize: 13 }}>{draft.notes.length}/{NOTES_MAX}</span>
        {fieldError("notes")}
      </div>
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : task ? "Save task" : "Add task"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

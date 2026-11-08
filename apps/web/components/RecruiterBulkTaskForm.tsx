"use client";

import { type FormEvent, useId, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { istInputToIso, nowIstInput } from "@/lib/bdmAppointments";
import type { PickOption } from "@/lib/lookups";
import { NOTE_MAX, TASK_TYPES, TASKS_URL, taskAssigneeSearch, TITLE_MAX } from "@/lib/recruiterCandidateTasks";

export type BulkSkip = { candidate_id: string; reason: string; message: string };
export type BulkTaskResult = { created: { candidate_id: string; task_id: string }[]; skipped: BulkSkip[] };

/** pob-019 (DEC-SCOPE-439 T9/T12): one hrc-016 task for every selected candidate, inline under the bulk bar. Times are entered in IST;
 *  a chosen requirement is linked to each task. The API checks every rule; Create is disabled while the request runs (T11). */
export default function RecruiterBulkTaskForm({ candidateIds, requirement, onDone, onCancel }: {
  candidateIds: string[]; requirement: PickOption | null; onDone: (result: BulkTaskResult) => void; onCancel: () => void;
}) {
  const id = useId();
  const [type, setType] = useState("");
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [notes, setNotes] = useState("");
  const [assignee, setAssignee] = useState<PickOption | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [now] = useState(nowIstInput);
  const n = candidateIds.length;
  const noun = n === 1 ? "candidate" : "candidates";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!assignee) return setError("Choose who the task is for.");
    setBusy(true);
    setError("");
    const body = {
      task_type: type, title: title.trim(), due_at: istInputToIso(due), assignee_user_id: assignee.id, candidate_ids: candidateIds,
      ...(notes.trim() ? { notes: notes.trim() } : {}), ...(requirement ? { job_id: requirement.id } : {}),
    };
    const outcome = await sendJson(`${TASKS_URL}/bulk`, "POST", body);
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    onDone(outcome.data as unknown as BulkTaskResult);
  }

  const fid = (name: string) => `${id}-${name}`;
  return (
    <form aria-label={`Assign a task to ${n} ${noun}`} onSubmit={submit} className="action-card" style={{ gap: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))", gap: 12 }}>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor={fid("type")}>Task type</label>
          <select id={fid("type")} required value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">Choose a type</option>
            {TASK_TYPES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor={fid("title")}>Title</label>
          <input id={fid("title")} required maxLength={TITLE_MAX} value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor={fid("due")}>Due (IST)</label>
          <input id={fid("due")} type="datetime-local" required min={now} value={due} onChange={(e) => setDue(e.target.value)} />
        </div>
        <SearchableSelect label="Assign to" noun="recruiter" required search={taskAssigneeSearch} onChange={setAssignee} />
      </div>
      <div className="field" style={{ marginBottom: 0 }}>
        <label htmlFor={fid("notes")}>Notes (optional)</label>
        <textarea id={fid("notes")} rows={2} maxLength={NOTE_MAX} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </div>
      {requirement && <p className="muted" style={{ margin: 0, fontSize: 13 }}>Each task is linked to {requirement.label}.</p>}
      {error && <p className="form-error" role="alert" style={{ margin: 0 }}>{error}</p>}
      <div className="actions" style={{ gap: 8 }}>
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Creating…" : `Create ${n} ${n === 1 ? "task" : "tasks"}`}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

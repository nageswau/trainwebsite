"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

import SchoolSkillAlert from "@/components/SchoolSkillAlert";
import { SkillStatus, useSkillAction } from "@/components/useSkillAction";
import { formatDate } from "@/lib/formatDate";
import { MODULE_LABEL, batchDraftErrors, type SkillBatch } from "@/lib/skills";

// ENH-011 spec §7: the batch as the page heading, its details, an inline edit, and close/reopen. A closed batch says what closing
// means; the sections below hide their write controls.
type Draft = { title: string; topic: string; trainer_name: string; start_date: string; end_date: string };
const draftOf = (b: SkillBatch): Draft => ({ title: b.title, topic: b.topic ?? "", trainer_name: b.trainer_name ?? "", start_date: b.start_date, end_date: b.end_date ?? "" });

export default function SchoolSkillBatchHeader({ batch }: { batch: SkillBatch }) {
  const url = `/api/v1/school/career-counselor/skill-batches/${batch.id}`;
  const action = useSkillAction();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft>(draftOf(batch));
  const editRef = useRef<HTMLButtonElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const returnFocus = useRef(false);

  useEffect(() => {
    if (editing) titleRef.current?.focus();
    else if (returnFocus.current) {
      returnFocus.current = false;
      editRef.current?.focus();
    }
  }, [editing]);

  function stopEditing() {
    returnFocus.current = true;
    setEditing(false);
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    const found = batchDraftErrors(draft);
    if (Object.keys(found).length > 0) return action.invalid(found);
    const body = { title: draft.title, topic: draft.topic.trim() || null, trainer_name: draft.trainer_name.trim() || null, start_date: draft.start_date, end_date: draft.end_date || null };
    if (await action.run(url, "PATCH", body, () => "Details saved.", { fieldsShown: true })) stopEditing();
  }

  const set = (name: keyof Draft) => (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [name]: e.target.value }));
  const invalid = (name: string) => (action.fields[name] ? { "aria-invalid": true as const, "aria-describedby": `skill-edit-${name}-error` } : {});
  const error = (name: string) => action.fields[name] && <span id={`skill-edit-${name}-error`} className="form-error">{action.fields[name]}</span>;
  const closed = batch.status === "closed";

  return (
    <div className="card" aria-busy={action.busy}>
      <p className="muted">{MODULE_LABEL[batch.module_type]} · {batch.school.name}</p>
      <h1>{batch.title}</h1>
      <p>
        {batch.end_date ? `${formatDate(batch.start_date)} – ${formatDate(batch.end_date)}` : `From ${formatDate(batch.start_date)}`}
        {batch.topic && <> · Topic: {batch.topic}</>}
        {batch.trainer_name && <> · Trainer: {batch.trainer_name}</>}
        {" "}<span className={closed ? "status pending" : "status"}>{closed ? "Closed" : "Open"}</span>
      </p>
      {closed && <p className="form-warning">This batch is closed. Reopen it to add students, sessions, attendance or scores.</p>}
      {!editing && (
        <div className="actions" style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          <button ref={editRef} type="button" className="btn secondary small" disabled={action.busy} onClick={() => { setDraft(draftOf(batch)); setEditing(true); }}>Edit details</button>
          <button type="button" className="btn secondary small" disabled={action.busy} onClick={() => void action.run(url, "PATCH", { status: closed ? "open" : "closed" }, () => (closed ? "Batch reopened." : "Batch closed."))}>
            {closed ? "Reopen batch" : "Close batch"}
          </button>
        </div>
      )}
      {editing && (
        <form className="form" onSubmit={save} noValidate>
          <div className="form-grid">
            <div className="field"><label htmlFor="skill-edit-title">Title</label><input id="skill-edit-title" ref={titleRef} className="search" required maxLength={160} value={draft.title} disabled={action.busy} onChange={set("title")} {...invalid("title")} />{error("title")}</div>
            <div className="field"><label htmlFor="skill-edit-topic">Topic (optional)</label><input id="skill-edit-topic" className="search" maxLength={120} value={draft.topic} disabled={action.busy} onChange={set("topic")} {...invalid("topic")} />{error("topic")}</div>
            <div className="field"><label htmlFor="skill-edit-trainer">Trainer name (optional)</label><input id="skill-edit-trainer" className="search" maxLength={120} value={draft.trainer_name} disabled={action.busy} onChange={set("trainer_name")} {...invalid("trainer_name")} />{error("trainer_name")}</div>
            <div className="field"><label htmlFor="skill-edit-start">Start date</label><input id="skill-edit-start" type="date" className="search" required value={draft.start_date} disabled={action.busy} onChange={set("start_date")} {...invalid("start_date")} />{error("start_date")}</div>
            <div className="field"><label htmlFor="skill-edit-end">End date (optional)</label><input id="skill-edit-end" type="date" className="search" min={draft.start_date} value={draft.end_date} disabled={action.busy} onChange={set("end_date")} {...invalid("end_date")} />{error("end_date")}</div>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            <button type="submit" className="btn small" disabled={action.busy}>{action.busy ? "Saving…" : "Save details"}</button>
            <button type="button" className="btn secondary small" disabled={action.busy} onClick={stopEditing}>Cancel</button>
          </div>
        </form>
      )}
      <SkillStatus message={action.message} />
      <SchoolSkillAlert alert={action.alert} />
    </div>
  );
}
